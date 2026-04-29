from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from app.utils.helpers import quantize_tb, bytes_to_tb

def parse_hour(key: str) -> Optional[int]:
    try:
        return datetime.strptime(key, "%Y-%m-%d %H:%M").hour
    except Exception:
        return None

def merge_hourly_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    def _sum_optional(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None and b is None: return None
        if a is None: return float(b)
        if b is None: return float(a)
        return float(a) + float(b)

    for sid, data in snapshot.items():
        name = data.get("name") or str(sid)
        entry = merged.setdefault(name, {"name": name, "outbound_bytes": None, "inbound_bytes": None})
        entry["outbound_bytes"] = _sum_optional(entry.get("outbound_bytes"), data.get("outbound_bytes"))
        entry["inbound_bytes"] = _sum_optional(entry.get("inbound_bytes"), data.get("inbound_bytes"))
    return merged

def merge_hourly_series(hourly: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {key: merge_hourly_snapshot(snapshot) for key, snapshot in hourly.items()}

def delta_by_name(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    aggregates: Dict[str, Dict[str, Any]] = {}
    prev_by_name = merge_hourly_snapshot(prev)
    curr_by_name = merge_hourly_snapshot(curr)
    for name, data in curr_by_name.items():
        prev_data = prev_by_name.get(name, {})
        prev_out, curr_out = prev_data.get("outbound_bytes"), data.get("outbound_bytes")
        prev_in, curr_in = prev_data.get("inbound_bytes"), data.get("inbound_bytes")
        out_delta = in_delta = None
        if prev_out is not None and curr_out is not None:
            out_delta = bytes_to_tb(float(curr_out) - float(prev_out)) if float(curr_out) >= float(prev_out) else bytes_to_tb(float(curr_out))
        if prev_in is not None and curr_in is not None:
            in_delta = bytes_to_tb(float(curr_in) - float(prev_in)) if float(curr_in) >= float(prev_in) else bytes_to_tb(float(curr_in))
        
        entry = aggregates.setdefault(name, {"out": Decimal("0.000"), "in": Decimal("0.000"), "has_out": False, "has_in": False})
        if out_delta is not None:
            entry["out"] += out_delta
            entry["has_out"] = True
        if in_delta is not None:
            entry["in"] += in_delta
            entry["has_in"] = True
    return aggregates

def compute_tracking_totals(hourly: Dict[str, Any], start_override: Optional[str] = None) -> Dict[str, Optional[str]]:
    keys = sorted(hourly.keys())
    if not keys: return {"start": None, "outbound_tb": "0.000", "inbound_tb": "0.000"}
    start_idx = 0
    start_label = keys[0]
    if start_override:
        for idx, key in enumerate(keys):
            if key >= start_override:
                start_idx, start_label = idx, start_override
                break
        else: return {"start": start_override, "outbound_tb": "0.000", "inbound_tb": "0.000"}
    
    total_out = total_in = Decimal("0.000")
    for i in range(start_idx + 1, len(keys)):
        deltas = delta_by_name(hourly.get(keys[i-1], {}), hourly.get(keys[i], {}))
        for data in deltas.values():
            if data.get("has_out"): total_out += data["out"]
            if data.get("has_in"): total_in += data["in"]
    return {"start": start_label, "outbound_tb": str(quantize_tb(total_out)), "inbound_tb": str(quantize_tb(total_in))}

def compute_cycle_data(hourly: Dict[str, Any], include_ids: Optional[Set[str]] = None, name_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    keys = sorted(hourly.keys())
    if len(keys) < 2: return {"servers": {}}
    server_ids = set()
    for snapshot in hourly.values(): server_ids.update(snapshot.keys())
    if include_ids: server_ids = {sid for sid in server_ids if str(sid) in include_ids}

    servers: Dict[str, Any] = {}
    for sid in server_ids:
        cycle_out = Decimal("0.000")
        cycle_age = 0
        points, rebuilds, name = [], [], name_map.get(str(sid)) if name_map else None
        for i in range(1, len(keys)):
            prev_key, curr_key = keys[i - 1], keys[i]
            prev, curr = hourly.get(prev_key, {}), hourly.get(curr_key, {})
            prev_data, curr_data = prev.get(sid), curr.get(sid)
            if curr_data and not name: name = curr_data.get("name") or str(sid)
            
            if prev_data and curr_data:
                p_out, c_out = prev_data.get("outbound_bytes"), curr_data.get("outbound_bytes")
                if p_out is not None and c_out is not None and float(c_out) < float(p_out):
                    cycle_out, cycle_age = Decimal("0.000"), 0
                    rebuilds.append(curr_key)

            deltas = delta_by_name(prev, curr)
            data = deltas.get(name or str(sid), {})
            total_out = data["out"] if data.get("has_out") else Decimal("0.000")
            cycle_out += total_out
            points.append({"time": curr_key, "out_tb_h": str(quantize_tb(total_out)), "cycle_out_cum_tb": str(quantize_tb(cycle_out)), "cycle_age_h": cycle_age, "hour_of_day": parse_hour(curr_key)})
            cycle_age += 1
        if points: servers[str(sid)] = {"name": name or str(sid), "points": points, "rebuilds": rebuilds}
    return {"servers": servers}

def detect_last_rebuilds(hourly: Dict[str, Any], name_map: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    keys = sorted(hourly.keys())
    last, prev_out = {}, {}
    name_to_id = {name: sid for sid, name in (name_map or {}).items()}
    for key in keys:
        snapshot = hourly.get(key, {})
        for sid, data in snapshot.items():
            out = data.get("outbound_bytes")
            if out is None: continue
            try: current = float(out)
            except Exception: continue
            name = data.get("name") or (name_map.get(str(sid)) if name_map else None) or str(sid)
            if name in prev_out and current < prev_out[name]:
                last[str(name_to_id.get(name) or name)] = key
            prev_out[name] = current
    return last

def summarize_rebuild_stats(state: Dict[str, Any]) -> Dict[str, Any]:
    stats = state.get("rebuild_stats", {}) or {}
    total = auto_total = 0
    last_event, last_time = None, None
    for name, entry in stats.items():
        total += int(entry.get("count") or 0)
        auto_total += int((entry.get("sources") or {}).get("流量超标自动重建") or 0)
        iso = entry.get("last_time_iso")
        if iso:
            try:
                parsed = datetime.fromisoformat(iso)
                if last_time is None or parsed > last_time:
                    last_time, last_event = parsed, {"time": entry.get("last_time"), "server": name, "source": entry.get("last_source"), "server_id": entry.get("last_server_id")}
            except Exception: pass
    return {"total": total, "auto_total": auto_total, "last": last_event, "stats": stats}
