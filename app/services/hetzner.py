import time
import threading
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.core.config import (
    CONFIG_PATH, QB_REBUILD_COOLDOWN_SECONDS, 
    CF_RETRY_ATTEMPTS, CF_RETRY_DELAY_SECONDS, 
    CF_REBUILD_SYNC_DELAY_SECONDS, save_yaml
)
from app.core.state import REBUILD_LOCKS, QB_COOLDOWN_UNTIL, get_now_local
from app.utils.helpers import (
    format_iso,
    get_server_location_name,
    parse_float_or_default,
    parse_int_or_default,
)
from app.services.cloudflare import resolve_cf_record, verify_dns_record

class HetznerClient:
    BASE_URL = "https://api.hetzner.cloud/v1"
    CF_API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        timeout = kwargs.pop("timeout", 20)
        resp = requests.request(method, url, headers=self.headers, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _request_paginated(self, endpoint: str, result_key: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        page, items = 1, []
        while True:
            data = self._request("GET", endpoint, params={**(params or {}), "page": page, "per_page": 50})
            chunk = data.get(result_key, [])
            if not chunk: break
            items.extend(chunk)
            pagination = data.get("meta", {}).get("pagination", {})
            if page >= int(pagination.get("last_page") or page): break
            page += 1
        return items

    def get_servers(self) -> List[Dict[str, Any]]: return self._request_paginated("servers", "servers")
    def get_server(self, server_id: int) -> Optional[Dict[str, Any]]:
        try: return self._request("GET", f"servers/{server_id}").get("server")
        except Exception: return None

    def get_server_metrics(self, server_id: int, start: str, end: str) -> Dict[str, Any]:
        try: return self._request("GET", f"servers/{server_id}/metrics", params={"type": "traffic", "start": start, "end": end}).get("metrics", {})
        except Exception: return {}

    def delete_server(self, server_id: int) -> bool:
        try: return self._request("DELETE", f"servers/{server_id}") and True
        except Exception: return False

    def power_on_server(self, server_id: int) -> bool:
        try: return self._request("POST", f"servers/{server_id}/actions/poweron") and True
        except Exception: return False

    def power_off_server(self, server_id: int) -> bool:
        try: return self._request("POST", f"servers/{server_id}/actions/poweroff") and True
        except Exception: return False

    def reboot_server(self, server_id: int) -> bool:
        try: return self._request("POST", f"servers/{server_id}/actions/reboot") and True
        except Exception: return False

    def get_snapshots(self) -> List[Dict[str, Any]]:
        try:
            snaps = self._request_paginated("images", "images", params={"type": "snapshot"})
            return sorted(snaps, key=lambda x: x.get("created", ""), reverse=True)
        except Exception: return []

    def rebuild_server(self, server_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        old = self.get_server(server_id)
        if not old: return {"success": False, "error": "服务器不存在"}
        
        image = config.get("rebuild", {}).get("snapshot_id_map", {}).get(str(server_id))
        if not image:
            snaps = self.get_snapshots()
            if not snaps: return {"success": False, "error": "无可用快照"}
            image = snaps[0]["id"]
            
        if not self.delete_server(server_id): return {"success": False, "error": "删除失败"}
        time.sleep(5)
        
        create_data = {
            "name": old["name"], "server_type": old["server_type"]["name"],
            "image": image, "location": get_server_location_name(old),
            "start_after_create": True
        }
        for _ in range(3):
            try:
                new = self._request("POST", "servers", json=create_data).get("server")
                if new: return {"success": True, "new_server_id": new["id"], "new_ip": new["public_net"]["ipv4"]["ip"], "snapshot_id": image}
            except Exception: time.sleep(5)
        return {"success": False, "error": "创建失败"}

    def update_cloudflare_a_record(self, api_token, zone_id, name, ip, attempts=3, delay=3) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        for _ in range(attempts):
            try:
                list_url = f"{self.CF_API_BASE}/zones/{zone_id}/dns_records"
                records = requests.get(list_url, headers=headers, params={"type": "A", "name": name}, timeout=15).json().get("result", [])
                if not records: return {"success": False, "error": "记录不存在"}
                
                upd_url = f"{self.CF_API_BASE}/zones/{zone_id}/dns_records/{records[0]['id']}"
                payload = {"type": "A", "name": name, "content": ip, "ttl": records[0].get("ttl", 1), "proxied": records[0].get("proxied", False)}
                requests.put(upd_url, headers=headers, json=payload, timeout=15).raise_for_status()
                return {"success": True}
            except Exception as e:
                if delay > 0: time.sleep(delay)
        return {"success": False, "error": "更新DNS失败"}

def integrate_time_series(series: List[List[Any]]) -> float:
    total = 0.0
    if not series or len(series) < 2: return 0.0
    for i in range(len(series) - 1):
        try:
            val = float(series[i][1])
            t1 = datetime.fromisoformat(series[i][0].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(series[i+1][0].replace("Z", "+00:00"))
            total += val * (t2 - t1).total_seconds()
        except Exception: continue
    return total

def get_today_traffic_bytes(client: HetznerClient, server_id: int) -> Dict[str, float]:
    now = get_now_local()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    metrics = client.get_server_metrics(server_id, format_iso(start), format_iso(now))
    ts = metrics.get("time_series", {})
    return {
        "out_bytes": integrate_time_series(ts.get("traffic.0.out", [])),
        "in_bytes": integrate_time_series(ts.get("traffic.0.in", [])),
    }

def perform_rebuild(server_id: int, server_name: str, config: Dict[str, Any], source: str, client: HetznerClient) -> Dict[str, Any]:
    lock = REBUILD_LOCKS.setdefault(str(server_id), threading.Lock())
    if not lock.acquire(blocking=False): return {"success": False, "error": "进行中"}
    try:
        result = client.rebuild_server(server_id, config)
        if result.get("success"):
             if QB_REBUILD_COOLDOWN_SECONDS > 0: QB_COOLDOWN_UNTIL[server_name] = time.time() + QB_REBUILD_COOLDOWN_SECONDS
             # 这里可以触发 DNS 更新和 TG 通知（由于解耦，建议在调用处处理或通过事件处理）
        return result
    finally: lock.release()
