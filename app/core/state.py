import threading
from typing import Any, Dict, Optional
from datetime import datetime

# 全局警报状态
ALERT_STATE: Dict[str, Dict[str, Optional[float]]] = {}

# 重建锁
REBUILD_LOCKS: Dict[str, threading.Lock] = {}

# 调度器状态
SCHEDULE_STATE: Dict[str, Any] = {"last_daily_report": None, "last_task_runs": {}}

# Bot 状态
BOT_STATE: Dict[str, Any] = {"update_offset": 0, "last_message_id": None, "last_message_text": None}

# qBittorrent 冷却时间
QB_COOLDOWN_UNTIL: Dict[str, float] = {}

def get_now_local() -> datetime:
    return datetime.now().astimezone()
