"""
Append-only NDJSON debug lines for browser/agent instrumentation.

Uses optional env ``USEIT_AGENT_NDJSON_LOG`` for output path; otherwise writes under
the repo ``logs/`` directory when discoverable, else skips silently.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping


def _default_log_path() -> Path | None:
    here = Path(__file__).resolve()
    for root in here.parents:
        logs = root / "logs" / "agent_ndjson_debug.ndjson"
        if (root / "pyproject.toml").is_file():
            try:
                logs.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                return None
            return logs
    return None


def write_agent_ndjson_line(
    *,
    hypothesisId: str,
    location: str,
    message: str,
    data: Mapping[str, Any] | None = None,
) -> None:
    """Append one JSON object per line; never raises to callers."""
    path = os.environ.get("USEIT_AGENT_NDJSON_LOG")
    target = Path(path) if path else _default_log_path()
    if not target:
        return
    try:
        payload = {
            "timestamp": time.time(),
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": dict(data) if data else {},
        }
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        with open(target, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
