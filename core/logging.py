"""Application logging setup."""

from datetime import datetime, timezone
import json
from typing import Any


def log(message: str, data: Any | None = None) -> None:
    log_data = {
        "time": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "data": data,
    }
    print(json.dumps(log_data, default=str), flush=True)
