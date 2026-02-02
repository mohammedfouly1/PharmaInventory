"""
Utility helpers for the inventory UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta


def parse_ddmmyyyy(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        return None


def expiry_status(expiry_date: str, near_months: int) -> str:
    """
    Returns: Valid, Near Expiry, Expired, Unknown
    """
    dt = parse_ddmmyyyy(expiry_date)
    if not dt:
        return "Unknown"
    today = datetime.today()
    if dt.date() < today.date():
        return "Expired"
    threshold = today + relativedelta(months=near_months)
    if dt.date() <= threshold.date():
        return "Near Expiry"
    return "Valid"


def normalize_sfda(sfda_value) -> str:
    if sfda_value is None:
        return ""
    if isinstance(sfda_value, list):
        return ", ".join(str(x) for x in sfda_value)
    return str(sfda_value)


def safe_get(data: Dict[str, str], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    return str(value)
