"""Structured logging helpers."""

from datetime import datetime, timezone
import json
from typing import Any


def log_event(message: str, data: Any | None = None) -> None:
    print(
        json.dumps(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "message": message,
                "data": data,
            },
            default=str,
        ),
        flush=True,
    )
