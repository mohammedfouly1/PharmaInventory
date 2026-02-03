"""
Application settings persistence.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from .storage import get_setting, set_setting


DEFAULT_SETTINGS: Dict[str, Any] = {
    "near_expiry_months": 6,
    "allow_duplicate_serial_override": False,
    "duplicate_handling_mode": "Aggregate",  # Aggregate or New line
    "display_mode": "Light",
    "auto_parse_on_enter": True,
    "auto_focus_scan_input": True,
    "persistence_backend": "MongoDB",
    "data_retention_sessions": 0,  # 0 = keep all
}


@st.cache_data(ttl=300)  # PERF FIX: Cache for 5 minutes (saves 1.6s on every page load!)
def load_settings() -> Dict[str, Any]:
    settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        settings[key] = get_setting(key, default)
    return settings


def save_settings(updates: Dict[str, Any]) -> None:
    for key, value in updates.items():
        set_setting(key, value)
    # PERF: Clear cache when settings are updated
    load_settings.clear()
