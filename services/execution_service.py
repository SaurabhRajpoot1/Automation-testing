"""Generic sandbox command execution service."""

from typing import Any

from services.sandbox_constants import REPO_PATH
from utils.docker_utils import ensure_container_running, exec_shell, get_container
from utils.logger import log_event


def execute_in_sandbox(
    container_id: str,
    command: str,
    workdir: str | None = None,
    detach: bool = False,
) -> dict[str, Any]:
    try:
        container = get_container(container_id)
        ensure_container_running(container)
        result = exec_shell(
            container,
            command,
            workdir=workdir or REPO_PATH,
            detach=detach,
        )
        response = {
            "container_id": container.id,
            "command": command,
            "workdir": workdir or REPO_PATH,
            **result.as_dict(),
        }
        log_event("Sandbox command executed", response)
        return response
    except Exception as exc:
        log_event("Sandbox command execution failed", {"container_id": container_id, "error": str(exc)})
        return {"error": str(exc)}
