"""
GS1 parser subprocess integration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Dict, Tuple


def parse_scan(scan_text: str) -> Tuple[bool, Dict[str, Any], str]:
    """
    Parse a scan string using the local gs1_parser module.

    Returns:
        (success, data, error_message)
    """
    if not scan_text:
        return False, {}, "Empty scan input"

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "gs1_parser",
                scan_text,
                "--json",
                "--lookup",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return False, {}, f"Failed to run parser: {exc}"

    if result.returncode != 0:
        return False, {}, result.stderr.strip() or "Parser error"

    try:
        data = json.loads(result.stdout)
        return True, data, ""
    except json.JSONDecodeError:
        return False, {}, "Parser returned invalid JSON"
