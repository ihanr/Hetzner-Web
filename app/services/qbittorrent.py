import requests
import time
from typing import Any, Dict, List
from app.core.state import QB_COOLDOWN_UNTIL

def normalize_qb_instances(qb_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    instances = qb_cfg.get("instances")
    if instances is None:
        url = qb_cfg.get("url")
        if url:
            instances = [{
                "name": qb_cfg.get("name"),
                "url": url,
                "username": qb_cfg.get("username"),
                "password": qb_cfg.get("password"),
                "verify_ssl": qb_cfg.get("verify_ssl", True),
                "timeout_seconds": qb_cfg.get("timeout_seconds"),
                "login_retries": qb_cfg.get("login_retries"),
                "login_retry_delay": qb_cfg.get("login_retry_delay"),
                "counter_mode": qb_cfg.get("counter_mode"),
            }]
    if not instances:
        return []
    normalized = []
    for entry in instances:
        if not isinstance(entry, dict): continue
        url = entry.get("url") or entry.get("base_url")
        if not url: continue
        normalized.append({
            "name": entry.get("name"),
            "url": url,
            "username": entry.get("username"),
            "password": entry.get("password"),
            "verify_ssl": entry.get("verify_ssl", True),
            "timeout_seconds": entry.get("timeout_seconds"),
            "login_retries": entry.get("login_retries"),
            "login_retry_delay": entry.get("login_retry_delay"),
            "counter_mode": entry.get("counter_mode"),
        })
    return normalized

def fetch_qb_instance(instance: Dict[str, Any], counter_mode: str) -> Dict[str, Any]:
    base_url = str(instance.get("url") or "").rstrip("/")
    name = instance.get("name") or base_url
    username = instance.get("username") or ""
    password = instance.get("password") or ""
    timeout = float(instance.get("timeout_seconds") or 6)
    login_retries = max(1, int(instance.get("login_retries") or 3))
    login_retry_delay = max(0, float(instance.get("login_retry_delay") or 3))
    verify_ssl = instance.get("verify_ssl", True)

    if not base_url or not username or not password:
        return {"name": name, "error": "配置缺失"}

    session = requests.Session()
    session.verify = verify_ssl
    logged_in = False
    for _ in range(login_retries):
        try:
            resp = session.post(f"{base_url}/api/v2/auth/login", data={"username": username, "password": password}, timeout=timeout)
            if resp.status_code == 200 and "Ok" in resp.text:
                logged_in = True
                break
        except Exception:
            pass
        if login_retry_delay > 0:
            time.sleep(login_retry_delay)
    
    if not logged_in:
        return {"name": name, "error": "登录失败"}

    try:
        resp = session.get(f"{base_url}/api/v2/transfer/info", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if counter_mode == "session":
            return {"name": name, "up": data.get("up_info_speed", 0), "dl": data.get("dl_info_speed", 0)}
        return {"name": name, "up": data.get("up_info_data", 0), "dl": data.get("dl_info_data", 0)}
    except Exception as e:
        return {"name": name, "error": str(e)}

def collect_qbittorrent_stats(config: Dict[str, Any]) -> Dict[str, Any]:
    qb_cfg = config.get("qbittorrent", {})
    if not qb_cfg or not qb_cfg.get("enabled"):
        return {"enabled": False}
    
    counter_mode = qb_cfg.get("counter_mode", "all")
    instances = normalize_qb_instances(qb_cfg)
    results = []
    for inst in instances:
        results.append(fetch_qb_instance(inst, counter_mode))
    
    return {"enabled": True, "instances": results, "counter_mode": counter_mode}
