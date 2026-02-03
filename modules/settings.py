"""
Application settings persistence.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

# PERF: Track settings operations
from modules.perf_tracker import track_event, track_function

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
@track_function
def load_settings() -> Dict[str, Any]:
    track_event("LOAD_SETTINGS_START", "Loading application settings (from cache or DB)")
    settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        settings[key] = get_setting(key, default)
    track_event("LOAD_SETTINGS_END", f"Loaded {len(settings)} settings")
    return settings


def save_settings(updates: Dict[str, Any]) -> None:
    for key, value in updates.items():
        set_setting(key, value)
    # PERF: Clear cache when settings are updated
    load_settings.clear()
