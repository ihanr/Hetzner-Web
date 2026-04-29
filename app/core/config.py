import os
import yaml
import json
import base64
import hmac
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC_DIR = os.path.join(APP_ROOT, "static")

CONFIG_PATH = os.environ.get("HETZNER_CONFIG_PATH", os.path.join(APP_ROOT, "config.yaml"))
WEB_CONFIG_PATH = os.environ.get("WEB_CONFIG_PATH", os.path.join(APP_ROOT, "web_config.json"))
THRESHOLD_STATE_PATH = os.environ.get("THRESHOLD_STATE_PATH", os.path.join(APP_ROOT, "threshold_state.json"))
REPORT_STATE_PATH = os.environ.get("REPORT_STATE_PATH", os.path.join(APP_ROOT, "report_state.json"))
REPORT_STATE_BACKUP_DIR = os.environ.get("REPORT_STATE_BACKUP_DIR", os.path.join(APP_ROOT, "report_state_backups"))
REPORT_STATE_BACKUP_KEEP = 3

def load_yaml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_yaml(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=False)

def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data: Dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)

def get_basic_auth(request: Request) -> Optional[tuple]:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "): return None
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        return tuple(decoded.split(":", 1)) if ":" in decoded else None
    except Exception: return None

def require_auth(request: Request) -> None:
    web_cfg = load_json(WEB_CONFIG_PATH)
    target_user = web_cfg.get("username", "admin")
    target_pass = web_cfg.get("password", "CHANGE_ME")
    auth = get_basic_auth(request)
    if not auth or not (hmac.compare_digest(auth[0], target_user) and hmac.compare_digest(auth[1], target_pass)):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
