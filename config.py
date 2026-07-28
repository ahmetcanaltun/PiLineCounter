"""Reading and writing config.json.

The device rewrites this file whenever the line, mode or counters change, so it
survives reboots. A missing or corrupt file is never fatal: the caller falls
back to its defaults and carries on counting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).parent / "config.json"


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """Saved settings, or an empty dict if there is nothing usable to read."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            settings = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Failed to load config: {exc}")
        return {}
    return settings if isinstance(settings, dict) else {}


def save(settings: dict[str, Any], path: Path = DEFAULT_PATH) -> None:
    """Persist settings, warning rather than raising if the write fails.

    A read-only filesystem or a full disk should not take down a counter that is
    otherwise working.
    """
    try:
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except OSError as exc:
        print(f"[WARN] Failed to save config: {exc}")
