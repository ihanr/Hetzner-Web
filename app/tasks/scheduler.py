import time
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP

from app.core.config import (
    CONFIG_PATH, load_yaml, save_yaml, load_json, REPORT_STATE_PATH,
    THRESHOLD_STATE_PATH, REPORT_STATE_BACKUP_DIR, REPORT_STATE_BACKUP_KEEP,
    save_json
)
from app.core.state import (
    SCHEDULE_STATE, ALERT_STATE, BOT_STATE, get_now_local
)
from app.services.hetzner import HetznerClient, perform_rebuild
from app.services.telegram import (
    handle_bot_command, handle_bot_callback, send_telegram_markdown,
    send_telegram_message, answer_telegram_callback, telegram_inline_keyboard,
    telegram_reply_keyboard_root, maybe_wrap_codeblock
)
from app.services.qbittorrent import collect_qbittorrent_stats
from app.utils.helpers import bytes_to_tb, parse_int_or_default

# -----------------------------------------------------------------------------
# 辅助逻辑 (统计与格式化)
# -----------------------------------------------------------------------------

def qb_instance_map(qb_stats: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {inst["name"]: inst for inst in qb_stats.get("instances", []) if "name" in inst}

def build_qb_compare_line(server_name: str, outgoing: Any, ingoing: Any, qb_map: Dict[str, Any]) -> str:
    inst = qb_map.get(server_name)
    if not inst or "error" in inst: return ""
    up_raw, dl_raw = inst.get("up", 0), inst.get("dl", 0)
    up_tb, dl_tb = bytes_to_tb(float(up_raw)), bytes_to_tb(float(dl_raw))
    return f"📊 qB统计: 📤 `{up_tb} TB` | 📥 `{dl_tb} TB`"

def parse_alert_levels(raw_levels: Any) -> List[int]:
    if not raw_levels: return [50, 80, 90, 95, 100]
    try:
        if isinstance(raw_levels, str):
            return sorted([int(x.strip()) for x in raw_levels.split(",") if x.strip()])
        return sorted([int(x) for x in raw_levels])
    except Exception: return [50, 80, 90, 95, 100]

def format_traffic_notification(name, out, _in, limit, percent, level, qb_line) -> str:
    out_tb = bytes_to_tb(float(out))
    msg = [f"⚠️ *流量预警 ({level}%)*", "", f"🖥 服务器: *{name}*", f"📈 当前使用: `{percent:.2f}%`", f"📤 已用上传: `{out_tb} TB` / {limit} TB"]
    if qb_line: msg.append(qb_line)
    return "\n".join(msg)

# -----------------------------------------------------------------------------
# 后台循环逻辑
# -----------------------------------------------------------------------------

def monitor_traffic_loop() -> None:
    print("[system] traffic monitor loop started")
    while True:
        try:
            config = load_yaml(CONFIG_PATH)
            traffic_cfg = config.get("traffic", {})
            telegram_cfg = config.get("telegram", {})
            limit_gb = traffic_cfg.get("limit_gb")
            if not limit_gb:
                time.sleep(60); continue

            limit_bytes = float(Decimal(limit_gb) * (1024**3))
            levels = parse_alert_levels(telegram_cfg.get("notify_levels"))
            client = HetznerClient(config["hetzner"]["api_token"])
            servers = client.get_servers()
            qb_stats = collect_qbittorrent_stats(config)
            qb_map = qb_instance_map(qb_stats) if qb_stats.get("enabled") else {}

            for s in servers:
                sid = str(s["id"])
                detail = client.get_server(s["id"]) or {}
                outgoing = detail.get("outgoing_traffic")
                if outgoing is None: continue
                
                percent = (float(outgoing) / limit_bytes) * 100
                state = ALERT_STATE.setdefault(sid, {"last_level": 0, "last_outgoing": None, "auto_rebuild": False})
                
                # 重置逻辑 (如果流量减少了说明可能手动重建过)
                if state["last_outgoing"] and float(outgoing) < state["last_outgoing"]:
                    state.update({"last_level": 0, "auto_rebuild": False})
                state["last_outgoing"] = float(outgoing)

                # 检查警报级别
                last_level = int(state.get("last_level") or 0)
                levels_to_send = [l for level in levels if last_level < (l := int(level)) <= percent]
                
                if levels_to_send and telegram_cfg.get("enabled"):
                    limit_tb = (Decimal(limit_bytes) / (1024**4)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                    qb_line = build_qb_compare_line(detail.get("name") or s.get("name") or sid, outgoing, detail.get("ingoing_traffic"), qb_map)
                    for level in levels_to_send:
                        text = format_traffic_notification(detail.get("name") or s.get("name") or sid, outgoing, detail.get("ingoing_traffic"), limit_tb, percent, level, qb_line)
                        if send_telegram_markdown(telegram_cfg.get("bot_token"), telegram_cfg.get("chat_id"), text):
                            state["last_level"] = level

                # 自动重建逻辑
                exceed_action = traffic_cfg.get("exceed_action", "")
                if float(outgoing) >= limit_bytes and not state.get("auto_rebuild"):
                    if exceed_action in ("rebuild", "delete_rebuild"):
                        perform_rebuild(s["id"], detail.get("name") or s.get("name") or sid, config, "流量超标自动重建", client)
                        state["auto_rebuild"] = True
                    elif exceed_action == "delete":
                        client.delete_server(s["id"])
                        state["auto_rebuild"] = True
                        
        except Exception as e:
            print(f"[monitor] error: {e}")
        time.sleep(max(30, int(load_yaml(CONFIG_PATH).get("traffic", {}).get("check_interval", 5)) * 60))

def telegram_bot_loop() -> None:
    print("[system] telegram bot loop started")
    while True:
        try:
            config = load_yaml(CONFIG_PATH)
            telegram_cfg = config.get("telegram", {})
            bot_token = telegram_cfg.get("bot_token")
            chat_id = str(telegram_cfg.get("chat_id", "")).strip()
            if not telegram_cfg.get("enabled") or not bot_token or not chat_id:
                time.sleep(10); continue

            offset = BOT_STATE.get("update_offset", 0)
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            resp = requests.get(url, params={"timeout": 25, "offset": offset}, timeout=30)
            if resp.status_code != 200: continue
            
            updates = resp.json().get("result", [])
            for update in updates:
                BOT_STATE["update_offset"] = update.get("update_id") + 1
                client = HetznerClient(config["hetzner"]["api_token"])
                
                # 处理回调 (Inline Keyboard)
                callback = update.get("callback_query")
                if callback:
                    cb_chat_id = str(callback.get("message", {}).get("chat", {}).get("id", "")).strip()
                    if cb_chat_id == chat_id:
                        reply, menu = handle_bot_callback(callback.get("data", ""), config, client)
                        answer_telegram_callback(bot_token, callback.get("id"))
                        send_telegram_markdown(bot_token, chat_id, maybe_wrap_codeblock(reply), reply_markup=telegram_inline_keyboard(menu))
                    continue
                
                # 处理普通消息
                msg = update.get("message")
                if msg and str(msg.get("chat", {}).get("id")) == chat_id and msg.get("text"):
                    reply = handle_bot_command(msg["text"], config, client)
                    menu = BOT_STATE.get("menu_state", "root")
                    send_telegram_markdown(bot_token, chat_id, maybe_wrap_codeblock(reply), reply_markup=telegram_inline_keyboard(menu))
                    if not BOT_STATE.get("reply_keyboard_enabled"):
                        send_telegram_message(bot_token, chat_id, "主菜单已激活", reply_markup=telegram_reply_keyboard_root())
                        BOT_STATE["reply_keyboard_enabled"] = True
                        
        except Exception as e:
            print(f"[bot] error: {e}")
        time.sleep(3)

def start_background_tasks():
    threading.Thread(target=monitor_traffic_loop, daemon=True).start()
    threading.Thread(target=telegram_bot_loop, daemon=True).start()
    # 定时任务 schedule_loop 可按需加入
    print("[system] all background threads initialized")
