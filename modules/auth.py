"""
Simple authentication utilities.
"""

from __future__ import annotations

from typing import Dict


DEFAULT_USERS = {
    "admin": "admin",
}


def validate_login(username: str, password: str, users: Dict[str, str] = None) -> bool:
    users = users or DEFAULT_USERS
    return users.get(username) == password
