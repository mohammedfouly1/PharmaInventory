"""
GTIN database lookup utilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


_DEFAULT_DB_PATH = Path(__file__).parent / "data" / "gtin_database.json"
_DB_CACHE: Optional[Dict[str, Any]] = None
_DB_CACHE_PATH: Optional[Path] = None


def _load_database(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load GTIN database JSON with a small in-process cache."""
    global _DB_CACHE, _DB_CACHE_PATH
    path = db_path or _DEFAULT_DB_PATH
    if _DB_CACHE is not None and _DB_CACHE_PATH == path:
        return _DB_CACHE

    data = json.loads(path.read_text(encoding="utf-8"))
    _DB_CACHE = data
    _DB_CACHE_PATH = path
    return data


def lookup_gtin(
    gtin: str,
    *,
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Lookup a GTIN in the local database and return the matching record.

    Args:
        gtin: GTIN string to search for (exact match).
        db_path: Optional path to gtin_database.json.

    Returns:
        The matching record dict, or None if not found.
    """
    if not gtin:
        return None

    db = _load_database(db_path)
    records = db.get("data", [])

    for record in records:
        if str(record.get("GTIN Code", "")).strip() == gtin:
            return record

    return None
