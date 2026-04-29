import socket
import requests
import time
from typing import Any, Dict, List, Optional
from app.utils.helpers import parse_int_or_default, parse_float_or_default

def resolve_cf_record(record_cfg: Any, fallback_zone: str, fallback_token: str) -> Optional[Dict[str, str]]:
    if isinstance(record_cfg, str):
        return {"record": record_cfg, "zone_id": fallback_zone, "api_token": fallback_token}
    if isinstance(record_cfg, dict):
        return {
            "record": record_cfg.get("record") or record_cfg.get("name"),
            "zone_id": record_cfg.get("zone_id") or fallback_zone,
            "api_token": record_cfg.get("api_token") or fallback_token,
        }
    return None

def verify_dns_record(record: str, expected_ip: str) -> Dict[str, Any]:
    try:
        socket.setdefaulttimeout(5)
        resolved = socket.gethostbyname(record)
        return {"success": True, "resolved": resolved, "match": resolved == expected_ip}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sync_cloudflare_records(config: Dict[str, Any], client) -> Dict[str, int]:
    cf_cfg = config.get("cloudflare", {}) or {}
    record_map = cf_cfg.get("record_map", {}) or {}
    if not cf_cfg.get("enabled") or not record_map:
        return {"updated": 0, "skipped": 0}

    servers = client.get_servers()
    updated = 0
    skipped = 0
    for s in servers:
        record_cfg = record_map.get(str(s["id"])) or record_map.get(s.get("name", ""))
        resolved = resolve_cf_record(record_cfg, cf_cfg.get("zone_id", ""), cf_cfg.get("api_token", ""))
        ip = s.get("public_net", {}).get("ipv4", {}).get("ip")
        if resolved and ip:
            result = client.update_cloudflare_a_record(
                resolved["api_token"],
                resolved["zone_id"],
                resolved["record"],
                ip,
                attempts=parse_int_or_default(cf_cfg.get("update_retries"), 3),
                delay_seconds=parse_float_or_default(cf_cfg.get("update_retry_delay"), 5),
            )
            if result.get("success"):
                updated += 1
            else:
                skipped += 1
        else:
            skipped += 1
    return {"updated": updated, "skipped": skipped}
