from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
from decimal import Decimal

from app.core.config import (
    require_auth, load_yaml, load_json, CONFIG_PATH, 
    REPORT_STATE_PATH, WEB_CONFIG_PATH
)
from app.core.state import get_now_local
from app.services.hetzner import HetznerClient, perform_rebuild
from app.services.qbittorrent import collect_qbittorrent_stats
from app.services.cloudflare import verify_dns_record
from app.utils.helpers import bytes_to_tb, get_server_location_name, quantize_tb
from app.utils.stats import (
    merge_hourly_series, compute_tracking_totals, detect_last_rebuilds,
    summarize_rebuild_stats, compute_cycle_data
)

router = APIRouter(prefix="/api")

@router.get("/servers")
def api_servers(request: Request):
    require_auth(request)
    config = load_yaml(CONFIG_PATH)
    client = HetznerClient(config["hetzner"]["api_token"])
    servers = client.get_servers()
    
    traffic_cfg = config.get("traffic", {})
    limit_gb = traffic_cfg.get("limit_gb")
    limit_tb = quantize_tb(Decimal(limit_gb) / Decimal(1024)) if limit_gb else None

    rows = []
    for s in servers:
        detail = client.get_server(s["id"]) or {}
        outgoing = detail.get("outgoing_traffic")
        ingoing = detail.get("ingoing_traffic")
        rows.append({
            "id": s["id"], "name": s["name"], "status": s["status"],
            "ip": s["public_net"]["ipv4"]["ip"] if s["public_net"].get("ipv4") else None,
            "server_type": s["server_type"]["name"], "location": get_server_location_name(s),
            "outbound_tb": str(bytes_to_tb(float(outgoing))) if outgoing else "0.000",
            "inbound_tb": str(bytes_to_tb(float(ingoing))) if ingoing else "0.000",
            "outbound_bytes": outgoing, "inbound_bytes": ingoing,
        })

    state = load_json(REPORT_STATE_PATH)
    web_cfg = load_json(WEB_CONFIG_PATH)
    hourly = merge_hourly_series(state.get("hourly", {}))
    tracking = compute_tracking_totals(hourly, web_cfg.get("tracking_start"))
    name_map = {str(s["id"]): s.get("name") or str(s["id"]) for s in servers}
    rebuilds = detect_last_rebuilds(state.get("hourly", {}), name_map)
    
    return {
        "servers": rows,
        "updated_at": get_now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "tracking": tracking,
        "traffic": {"limit_gb": limit_gb, "limit_tb": str(limit_tb) if limit_tb else None, "cost_per_tb_eur": 1},
        "rebuilds": rebuilds,
        "rebuild_summary": summarize_rebuild_stats(state),
    }

@router.get("/qb")
def api_qb(request: Request):
    require_auth(request)
    config = load_yaml(CONFIG_PATH)
    return collect_qbittorrent_stats(config)

@router.post("/rebuild")
async def api_rebuild(request: Request):
    require_auth(request)
    payload = await request.json()
    server_id = int(payload.get("server_id"))
    config = load_yaml(CONFIG_PATH)
    client = HetznerClient(config["hetzner"]["api_token"])
    detail = client.get_server(server_id) or {}
    name = detail.get("name") or str(server_id)
    result = perform_rebuild(server_id, name, config, "Web API", client)
    if not result.get("success"):
        return JSONResponse(result, status_code=500)
    return {"rebuild": result, "dns": result.get("dns")}

@router.get("/cycle")
def api_cycle(request: Request):
    require_auth(request)
    state = load_json(REPORT_STATE_PATH)
    config = load_yaml(CONFIG_PATH)
    client = HetznerClient(config["hetzner"]["api_token"])
    servers = client.get_servers()
    include_ids = {str(s["id"]) for s in servers}
    name_map = {str(s["id"]): s.get("name") or str(s["id"]) for s in servers}
    return compute_cycle_data(state.get("hourly", {}), include_ids=include_ids, name_map=name_map)
