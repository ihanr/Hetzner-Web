from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional, List, Any

def bytes_to_tb(value_bytes: float) -> Decimal:
    return (Decimal(value_bytes) / (Decimal(1024) ** 4)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )

def quantize_tb(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

def bytes_to_gb(value_bytes: float) -> Decimal:
    return (Decimal(value_bytes) / (Decimal(1024) ** 3)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

def bytes_to_tb_precise(value_bytes: float, places: str = "0.000") -> Decimal:
    return (Decimal(value_bytes) / (Decimal(1024) ** 4)).quantize(
        Decimal(places), rounding=ROUND_HALF_UP
    )

def format_iso(dt: datetime) -> str:
    return dt.isoformat()

def parse_int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def parse_float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def progress_bar(percent: float) -> str:
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)
