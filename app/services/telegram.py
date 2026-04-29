import requests
import socket
import threading
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.core.state import BOT_STATE, get_now_local, ALERT_STATE
from app.core.config import CONFIG_PATH, load_yaml, save_yaml, load_json, REPORT_STATE_PATH, save_json
from app.utils.helpers import (
    bytes_to_tb, bytes_to_tb_precise, progress_bar, 
    parse_int_or_default, parse_float_or_default
)
from app.services.cloudflare import sync_cloudflare_records, resolve_cf_record
from app.services.hetzner import get_today_traffic_bytes, perform_rebuild
from app.utils.stats import summarize_rebuild_stats, compute_tracking_totals

# -----------------------------------------------------------------------------
# 基础发送函数
# -----------------------------------------------------------------------------

def send_telegram_message(bot_token, chat_id, text, reply_markup=None):
    if not bot_token or not chat_id: return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text, "reply_markup": reply_markup}, timeout=15)
        return resp.status_code < 400
    except Exception: return False

def send_telegram_markdown(bot_token, chat_id, text, reply_markup=None):
    if not bot_token or not chat_id: return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": reply_markup}, timeout=15)
        if resp.status_code >= 400: return send_telegram_message(bot_token, chat_id, text, reply_markup)
        return True
    except Exception: return False

def answer_telegram_callback(bot_token, callback_id):
    if not bot_token or not callback_id: return
    try: requests.post(f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery", json={"callback_query_id": callback_id}, timeout=10)
    except Exception: pass

def maybe_wrap_codeblock(text):
    if not BOT_STATE.get("code_mode") or "```" in text: return text
    return f"```text\n{text}\n```"

# -----------------------------------------------------------------------------
# 键盘与菜单
# -----------------------------------------------------------------------------

def telegram_reply_keyboard_root():
    return {"keyboard": [["📊 查询类", "🔧 控制类"], ["💾 快照管理", "⏰ 定时任务"], ["🧾 代码块模式", "📖 命令大全"]], "resize_keyboard": True}

def telegram_inline_keyboard(menu):
    m_map = {
        "query": [[{"text": "🖥 列表", "callback_data": "cmd:/list"}, {"text": "📈 状态", "callback_data": "cmd:/status"}], [{"text": "📊 流量", "callback_data": "cmd:/traffic"}, {"text": "📅 今日", "callback_data": "cmd:/today"}]],
        "control": [[{"text": "▶️ 启动", "callback_data": "prompt:/startserver"}, {"text": "⏸️ 停止", "callback_data": "prompt:/stopserver"}], [{"text": "🔄 重启", "callback_data": "prompt:/reboot"}, {"text": "🔨 重建", "callback_data": "prompt:/rebuild"}]],
    }
    kb = m_map.get(menu, [[{"text": "📊 查询菜单", "callback_data": "menu:query"}, {"text": "🔧 控制菜单", "callback_data": "menu:control"}]])
    if menu != "root": kb.append([{"text": "🏠 返回主菜单", "callback_data": "menu:root"}])
    return {"inline_keyboard": kb}

# -----------------------------------------------------------------------------
# 业务汇报逻辑
# -----------------------------------------------------------------------------

def build_manual_report(config, client) -> str:
    now, state = get_now_local(), load_json(REPORT_STATE_PATH)
    servers = client.get_servers()
    parts = [f"🕒 *流量快报 ({now.strftime('%H:%M')})*"]
    for s in servers:
        detail = client.get_server(s["id"]) or {}
        out = detail.get("outgoing_traffic")
        parts.append(f"🖥 *{detail.get('name', s['id'])}*: `{bytes_to_tb(float(out)) if out else 0} TB`")
    return "\n".join(parts)

# -----------------------------------------------------------------------------
# 指令处理器
# -----------------------------------------------------------------------------

def handle_bot_command(text, config, client) -> str:
    cmd = (text or "").strip()
    mapping = {"📊 查询类": "__menu_query__", "🔧 控制类": "__menu_control__", "🏠 返回主菜单": "__menu_root__", "🧾 代码块模式": "__toggle_code__", "📖 命令大全": "/help"}
    cmd = mapping.get(cmd, cmd)

    if cmd.startswith("__menu_"):
        BOT_STATE["menu_state"] = cmd.split("_")[2]; return "🏠 菜单已切换"
    
    parts = cmd.split()
    if not parts: return "⚠️ 请输入指令"
    command = parts[0].lower()
    args = parts[1:]

    if command in ("/start", "/help"): return "📖 **Hetzner 控制台**\n使用下方菜单或输入 /list 查看服务器"

    if command == "/list":
        ss = client.get_servers()
        return "\n".join([f"• *{s['name']}* (`{s['id']}`): {s['status']}" for s in ss]) if ss else "📭 无服务器"

    if command == "/status":
        ss = client.get_servers()
        rebuilds = summarize_rebuild_stats(load_json(REPORT_STATE_PATH))
        return f"📊 *系统状态*\n服务器: {len(ss)} 台\n总重建: {rebuilds['total']} 次"

    if command == "/today":
        ss = client.get_servers()
        lines = ["📅 *今日流量统计*"]
        for s in ss:
            usage = get_today_traffic_bytes(client, s["id"])
            lines.append(f"• {s['name']}: 📤 {bytes_to_tb_precise(usage['out_bytes'])} TB")
        return "\n".join(lines)

    if command == "/report": return build_manual_report(config, client)
    
    if command == "/rebuild" and args:
        res = perform_rebuild(int(args[0]), "Manual", config, "TG指令", client)
        return "✅ 已触发重建" if res.get("success") else f"❌ 失败: {res.get('error')}"

    return f"收到指令: {command}，正在完善中..."

def handle_bot_callback(data, config, client):
    if data.startswith("menu:"): return "已切换", data.split(":")[1]
    if data.startswith("cmd:"): return handle_bot_command(data.split(":")[1], config, client), BOT_STATE.get("menu_state", "root")
    if data.startswith("prompt:"): 
        BOT_STATE["pending_cmd"] = data.split(":")[1]
        return "请输入 ID:", "root"
    return "未知操作", "root"
