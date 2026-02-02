"""
MongoDB persistence layer for inventory sessions.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
JSON_PATH = DATA_DIR / "app.json"
PERSISTENCE_BACKEND = os.getenv("PERSISTENCE_BACKEND", "")
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://mohammedfouly:bousia11BB@mongodbcleuster.regz0gp.mongodb.net/?appName=MongoDbCleuster",
)
MONGODB_DB = os.getenv("MONGODB_DB", "DrugInventory")

_client: Optional[MongoClient] = None


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        if not MONGODB_URI:
            raise ValueError("MONGODB_URI is required for MongoDB backend.")
        _client = MongoClient(MONGODB_URI)
    return _client


def get_db():
    return _get_client()[MONGODB_DB]


def _backend() -> str:
    if PERSISTENCE_BACKEND:
        return PERSISTENCE_BACKEND.strip().lower()
    if not MONGODB_URI:
        return "json"
    return "mongodb"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _json_load() -> Dict[str, Any]:
    _ensure_data_dir()
    if not JSON_PATH.exists():
        return {"sessions": [], "lines": [], "audit": [], "settings": {}}
    with JSON_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _json_save(payload: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def init_db() -> None:
    if _backend() == "json":
        _json_save(_json_load())
        return
    db = get_db()
    db.sessions.create_index("session_id", unique=True)
    db.sessions.create_index("start_datetime")
    db.lines.create_index([("session_id", ASCENDING), ("scan_timestamp", DESCENDING)])
    db.lines.create_index(
        [
            ("session_id", ASCENDING),
            ("gtin", ASCENDING),
            ("batch_lot", ASCENDING),
            ("expiry_date", ASCENDING),
        ]
    )
    db.lines.create_index([("session_id", ASCENDING), ("serial", ASCENDING)])
    db.audit.create_index([("session_id", ASCENDING), ("timestamp", DESCENDING)])
    db.settings.create_index("key", unique=True)


def check_connection() -> bool:
    if _backend() == "json":
        return True
    try:
        _get_client().admin.command("ping")
        return True
    except PyMongoError:
        return False


def set_setting(key: str, value: Any) -> None:
    if _backend() == "json":
        payload = _json_load()
        payload["settings"][key] = value
        _json_save(payload)
        return
    db = get_db()
    db.settings.update_one(
        {"_id": key},
        {"$set": {"key": key, "value": value}},
        upsert=True,
    )


def get_setting(key: str, default: Any = None) -> Any:
    if _backend() == "json":
        payload = _json_load()
        return payload.get("settings", {}).get(key, default)
    db = get_db()
    doc = db.settings.find_one({"_id": key})
    if not doc:
        return default
    return doc.get("value", default)


def _prune_sessions(retain_count: int) -> None:
    if retain_count <= 0:
        return
    if _backend() == "json":
        payload = _json_load()
        sessions = payload.get("sessions", [])
        sessions_sorted = sorted(
            sessions,
            key=lambda s: s.get("start_datetime", ""),
            reverse=True,
        )
        keep_ids = {s["session_id"] for s in sessions_sorted[:retain_count]}
        payload["sessions"] = [s for s in sessions if s["session_id"] in keep_ids]
        payload["lines"] = [l for l in payload.get("lines", []) if l.get("session_id") in keep_ids]
        payload["audit"] = [a for a in payload.get("audit", []) if a.get("session_id") in keep_ids]
        _json_save(payload)
        return
    db = get_db()
    cursor = db.sessions.find().sort("start_datetime", DESCENDING).skip(retain_count)
    old_ids = [doc["_id"] for doc in cursor]
    if not old_ids:
        return
    db.sessions.delete_many({"_id": {"$in": old_ids}})
    db.lines.delete_many({"session_id": {"$in": old_ids}})
    db.audit.delete_many({"session_id": {"$in": old_ids}})


def create_session(data: Dict[str, Any]) -> str:
    session_id = data.get("session_id") or str(uuid4())
    doc = {
        "_id": session_id,
        "session_id": session_id,
        "session_name": data.get("session_name"),
        "counter_name": data.get("counter_name"),
        "location": data.get("location"),
        "inventory_type": data.get("inventory_type"),
        "start_datetime": data.get("start_datetime") or _utc_now(),
        "device_id": data.get("device_id"),
        "notes": data.get("notes"),
        "status": data.get("status") or "In Progress",
        "last_opened": _utc_now(),
    }
    if _backend() == "json":
        payload = _json_load()
        payload["sessions"].append(doc.copy())
        _json_save(payload)
    else:
        db = get_db()
        db.sessions.insert_one(doc)
    set_setting("last_session_id", session_id)
    retention = int(get_setting("data_retention_sessions", 0) or 0)
    _prune_sessions(retention)
    return session_id


def update_session(session_id: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    if _backend() == "json":
        payload = _json_load()
        for session in payload.get("sessions", []):
            if session.get("session_id") == session_id:
                session.update(updates)
                break
        _json_save(payload)
        return
    db = get_db()
    db.sessions.update_one({"_id": session_id}, {"$set": updates})


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if _backend() == "json":
        payload = _json_load()
        for doc in payload.get("sessions", []):
            if doc.get("session_id") == session_id:
                return dict(doc)
        return None
    db = get_db()
    doc = db.sessions.find_one({"_id": session_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def list_sessions(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if _backend() == "json":
        payload = _json_load()
        sessions = sorted(
            payload.get("sessions", []),
            key=lambda s: s.get("start_datetime", ""),
            reverse=True,
        )
        if limit:
            sessions = sessions[:limit]
        return [dict(s) for s in sessions]
    db = get_db()
    cursor = db.sessions.find().sort("start_datetime", DESCENDING)
    if limit:
        cursor = cursor.limit(limit)
    docs = []
    for doc in cursor:
        doc.pop("_id", None)
        docs.append(doc)
    return docs


def create_line(data: Dict[str, Any]) -> str:
    line_id = data.get("line_id") or str(uuid4())
    doc = {
        "_id": line_id,
        "line_id": line_id,
        "session_id": data.get("session_id"),
        "scan_timestamp": data.get("scan_timestamp") or _utc_now(),
        "scanned_by": data.get("scanned_by"),
        "gtin": data.get("gtin") or "",
        "trade_name": data.get("trade_name"),
        "scientific_name": data.get("scientific_name"),
        "batch_lot": data.get("batch_lot") or "",
        "expiry_date": data.get("expiry_date") or "",
        "serial": data.get("serial") or "",
        "on_hand_count": data.get("on_hand_count"),
        "count_unit": data.get("count_unit"),
        "unit_type": data.get("unit_type"),
        "granular_unit": data.get("granular_unit"),
        "dosage_form": data.get("dosage_form"),
        "strength": data.get("strength"),
        "roa": data.get("roa"),
        "package_type": data.get("package_type"),
        "package_size": data.get("package_size"),
        "category": data.get("category"),
        "price": data.get("price"),
        "sfda_code": data.get("sfda_code"),
        "status": data.get("status"),
        "notes": data.get("notes"),
        "locked": bool(data.get("locked", False)),
    }
    if _backend() == "json":
        payload = _json_load()
        payload["lines"].append(doc.copy())
        _json_save(payload)
    else:
        db = get_db()
        db.lines.insert_one(doc)
    return line_id


def update_line(line_id: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    if _backend() == "json":
        payload = _json_load()
        for line in payload.get("lines", []):
            if line.get("line_id") == line_id:
                line.update(updates)
                break
        _json_save(payload)
        return
    db = get_db()
    db.lines.update_one({"_id": line_id}, {"$set": updates})


def delete_line(line_id: str) -> None:
    if _backend() == "json":
        payload = _json_load()
        payload["lines"] = [l for l in payload.get("lines", []) if l.get("line_id") != line_id]
        _json_save(payload)
        return
    db = get_db()
    db.lines.delete_one({"_id": line_id})


def list_lines(session_id: str) -> List[Dict[str, Any]]:
    if _backend() == "json":
        payload = _json_load()
        lines = [l for l in payload.get("lines", []) if l.get("session_id") == session_id]
        lines = sorted(lines, key=lambda l: l.get("scan_timestamp", ""), reverse=True)
        return [dict(l) for l in lines]
    db = get_db()
    cursor = db.lines.find({"session_id": session_id}).sort("scan_timestamp", DESCENDING)
    docs = []
    for doc in cursor:
        doc.pop("_id", None)
        docs.append(doc)
    return docs


def find_duplicates(
    session_id: str,
    *,
    gtin: str,
    batch_lot: str,
    expiry_date: str,
) -> List[Dict[str, Any]]:
    if _backend() == "json":
        payload = _json_load()
        matches = [
            l
            for l in payload.get("lines", [])
            if l.get("session_id") == session_id
            and (l.get("gtin") or "") == (gtin or "")
            and (l.get("batch_lot") or "") == (batch_lot or "")
            and (l.get("expiry_date") or "") == (expiry_date or "")
        ]
        return [dict(m) for m in matches]
    db = get_db()
    cursor = db.lines.find(
        {
            "session_id": session_id,
            "gtin": gtin or "",
            "batch_lot": batch_lot or "",
            "expiry_date": expiry_date or "",
        }
    )
    docs = []
    for doc in cursor:
        doc.pop("_id", None)
        docs.append(doc)
    return docs


def find_serial_duplicates(session_id: str, serial: str) -> List[Dict[str, Any]]:
    if not serial:
        return []
    if _backend() == "json":
        payload = _json_load()
        matches = [
            l
            for l in payload.get("lines", [])
            if l.get("session_id") == session_id and l.get("serial") == serial
        ]
        return [dict(m) for m in matches]
    db = get_db()
    cursor = db.lines.find({"session_id": session_id, "serial": serial})
    docs = []
    for doc in cursor:
        doc.pop("_id", None)
        docs.append(doc)
    return docs


def create_audit(
    username: str,
    action_type: str,
    session_id: Optional[str] = None,
    line_id: Optional[str] = None,
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> str:
    audit_id = str(uuid4())
    doc = {
        "_id": audit_id,
        "audit_id": audit_id,
        "timestamp": _utc_now(),
        "username": username,
        "action_type": action_type,
        "session_id": session_id,
        "line_id": line_id,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
    }
    if _backend() == "json":
        payload = _json_load()
        payload["audit"].append(doc.copy())
        _json_save(payload)
    else:
        db = get_db()
        db.audit.insert_one(doc)
    return audit_id


def list_audit(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if _backend() == "json":
        payload = _json_load()
        records = payload.get("audit", [])
        if session_id:
            records = [r for r in records if r.get("session_id") == session_id]
        records = sorted(records, key=lambda r: r.get("timestamp", ""), reverse=True)
        return [dict(r) for r in records]
    db = get_db()
    query = {"session_id": session_id} if session_id else {}
    cursor = db.audit.find(query).sort("timestamp", DESCENDING)
    docs = []
    for doc in cursor:
        doc.pop("_id", None)
        docs.append(doc)
    return docs
