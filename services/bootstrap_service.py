"""Sandbox dependency installation and application runtime bootstrap."""

import json
import shlex
from typing import Any

from services.playwright_service import ensure_playwright_config
from services.sandbox_constants import (
    APP_LOG_PATH,
    APP_PID_PATH,
    BOOTSTRAP_STATE_PATH,
    REPO_PATH,
)
from utils.docker_utils import (
    ensure_container_running,
    exec_shell,
    exec_shell_or_raise,
    get_container,
    get_mapped_ports,
    put_text_file,
)
from utils.logger import log_event

STACK_DETECTION_SCRIPT = f"""
import json
from pathlib import Path

root = Path({REPO_PATH!r})
ignored_parts = {{".git", ".venv", "__pycache__", "build", "dist", "node_modules", "venv"}}


def should_ignore(path):
    return any(part in ignored_parts for part in path.parts)


def find_files(filename, max_depth=2):
    matches = []
    for path in root.rglob(filename):
        if should_ignore(path):
            continue
        depth = len(path.relative_to(root).parts) - 1
        if depth <= max_depth:
            matches.append(str(path.relative_to(root)))
    return sorted(matches)


def exists_any(names):
    return [name for name in names if (root / name).exists()]


package_files = find_files("package.json")
requirements_files = find_files("requirements.txt")
pyproject = root / "pyproject.toml"
setup_py = root / "setup.py"
vite_files = exists_any(["vite.config.js", "vite.config.ts", "vite.config.mjs"])
next_files = exists_any(["next.config.js", "next.config.mjs", "next.config.ts"])
docker_files = exists_any(["Dockerfile", "dockerfile"])
compose_files = exists_any(["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"])

stacks = []
if package_files:
    stacks.append("node")
if vite_files:
    stacks.append("vite")
if next_files:
    stacks.append("nextjs")
if requirements_files or pyproject.exists() or setup_py.exists():
    stacks.append("python3")
if docker_files:
    stacks.append("docker")
if compose_files:
    stacks.append("docker-compose")

print(json.dumps({{
    "stacks": stacks or ["unknown"],
    "package_files": package_files,
    "requirements_files": requirements_files,
    "has_pyproject": pyproject.exists(),
    "has_setup_py": setup_py.exists(),
    "vite_files": vite_files,
    "next_files": next_files,
    "docker_files": docker_files,
    "docker_compose_files": compose_files,
}}))
"""

RUNTIME_SELECTION_SCRIPT = f"""
import json
from pathlib import Path

root = Path({REPO_PATH!r})
ignored_parts = {{".git", ".venv", "__pycache__", "build", "dist", "node_modules", "venv"}}


def should_ignore(path):
    return any(part in ignored_parts for part in path.parts)


def find_files(filename, max_depth=2):
    matches = []
    for path in root.rglob(filename):
        if should_ignore(path):
            continue
        depth = len(path.relative_to(root).parts) - 1
        if depth <= max_depth:
            matches.append(path)
    return sorted(matches)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {{}}


for package_file in find_files("package.json"):
    package_dir = package_file.parent
    package = load_json(package_file)
    scripts = package.get("scripts") or {{}}
    dependencies = package.get("dependencies") or {{}}
    dev_dependencies = package.get("devDependencies") or {{}}
    all_dependencies = {{**dependencies, **dev_dependencies}}
    dev_script = scripts.get("dev", "")

    if "dev" in scripts and (
        "vite" in all_dependencies
        or "vite" in dev_script
        or (package_dir / "vite.config.js").exists()
        or (package_dir / "vite.config.ts").exists()
        or (package_dir / "vite.config.mjs").exists()
    ):
        print(json.dumps({{
            "type": "node",
            "framework": "vite",
            "command": "npm run dev -- --host 0.0.0.0",
            "workdir": str(package_dir),
            "port": 5173,
            "reason": "Vite project detected",
        }}))
        raise SystemExit

    if "dev" in scripts and (
        "next" in all_dependencies
        or "next" in dev_script
        or (package_dir / "next.config.js").exists()
        or (package_dir / "next.config.mjs").exists()
        or (package_dir / "next.config.ts").exists()
    ):
        print(json.dumps({{
            "type": "node",
            "framework": "nextjs",
            "command": "npm run dev -- -H 0.0.0.0",
            "workdir": str(package_dir),
            "port": 3000,
            "reason": "Next.js project detected",
        }}))
        raise SystemExit

    if "start" in scripts:
        print(json.dumps({{
            "type": "node",
            "framework": "react",
            "command": "HOST=0.0.0.0 npm start",
            "workdir": str(package_dir),
            "port": 3000,
            "reason": "package.json start script detected",
        }}))
        raise SystemExit

    if "dev" in scripts:
        print(json.dumps({{
            "type": "node",
            "framework": "node",
            "command": "npm run dev -- --host 0.0.0.0",
            "workdir": str(package_dir),
            "port": 3000,
            "reason": "package.json dev script detected",
        }}))
        raise SystemExit


if (root / "main.py").exists():
    print(json.dumps({{
        "type": "python3",
        "framework": "fastapi",
        "command": "python3 -m uvicorn main:app --host 0.0.0.0 --port 8000",
        "workdir": str(root),
        "port": 8000,
        "reason": "main.py detected",
    }}))
    raise SystemExit

if (root / "app" / "main.py").exists():
    print(json.dumps({{
        "type": "python3",
        "framework": "fastapi",
        "command": "python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000",
        "workdir": str(root),
        "port": 8000,
        "reason": "app/main.py detected",
    }}))
    raise SystemExit

print(json.dumps({{
    "type": "unknown",
    "framework": None,
    "command": None,
    "workdir": str(root),
    "port": None,
    "reason": "No known app start command detected",
}}))
"""

INSTALL_DEPENDENCIES_COMMAND = f"""
set -eux
cd {REPO_PATH}

find . -maxdepth 2 -name requirements.txt -not -path "*/.venv/*" -print | while read req_file; do
    python3 -m pip install -r "$req_file"
done

if [ -f pyproject.toml ] || [ -f setup.py ]; then
    python3 -m pip install -e .
fi

package_count=$(find . -maxdepth 2 -name package.json -not -path "*/node_modules/*" | wc -l | tr -d ' ')
if [ "$package_count" -eq 0 ]; then
    npm init -y
    npm install -D @playwright/test
else
    find . -maxdepth 2 -name package.json -not -path "*/node_modules/*" -print | while read package_file; do
        project_dir="$(dirname "$package_file")"
        cd "{REPO_PATH}/$project_dir"
        npm install
        npm install -D @playwright/test
        cd {REPO_PATH}
    done
fi
"""


def bootstrap_sandbox(container_id: str) -> dict[str, Any]:
    try:
        container = get_container(container_id)
        ensure_container_running(container)

        log_event("Sandbox bootstrap started", {"container_id": container.id})
        detection = detect_stack(container)
        install_dependencies(container)
        runtime = select_runtime(container)
        app = start_application(container, runtime)

        base_url = app.get("container_url")
        ensure_playwright_config(container, base_url=base_url)

        ports = get_mapped_ports(container)
        attach_host_app_url(app, runtime, ports)
        state = {
            "container_id": container.id,
            "repo_path": REPO_PATH,
            "detected": detection,
            "runtime": runtime,
            "app": app,
            "ports": ports,
            "healthy": app.get("healthy", False),
        }
        put_text_file(container, BOOTSTRAP_STATE_PATH, json.dumps(state, indent=2))

        log_event("Sandbox bootstrap completed", state)
        return {
            **state,
            "status": "healthy" if app.get("healthy") else "bootstrap failed health check",
            "url": app.get("host_url") or app.get("container_url"),
        }
    except Exception as exc:
        log_event("Sandbox bootstrap failed", {"container_id": container_id, "error": str(exc)})
        return {"error": str(exc)}


def detect_stack(container) -> dict[str, Any]:
    log_event("Detecting sandbox stack", {"container_id": container.id})
    result = exec_shell_or_raise(container, f"python3 - <<'PY'\n{STACK_DETECTION_SCRIPT}\nPY")
    return json.loads(result.stdout.strip().splitlines()[-1])


def install_dependencies(container) -> None:
    log_event("Installing sandbox dependencies", {"container_id": container.id})
    exec_shell_or_raise(container, INSTALL_DEPENDENCIES_COMMAND)
    log_event("Sandbox dependencies installed", {"container_id": container.id})


def select_runtime(container) -> dict[str, Any]:
    log_event("Selecting app runtime command", {"container_id": container.id})
    result = exec_shell_or_raise(container, f"python3 - <<'PY'\n{RUNTIME_SELECTION_SCRIPT}\nPY")
    runtime = json.loads(result.stdout.strip().splitlines()[-1])
    log_event("App runtime selected", {"container_id": container.id, "runtime": runtime})
    return runtime


def start_application(container, runtime: dict[str, Any]) -> dict[str, Any]:
    command = runtime.get("command")
    port = runtime.get("port")
    workdir = runtime.get("workdir") or REPO_PATH

    if not command or not port:
        return {
            "started": False,
            "healthy": False,
            "reason": runtime.get("reason", "No known app start command detected"),
        }

    pid = start_background_process(container, command, workdir)
    health = wait_for_app_health(container, int(port))
    app = {
        "started": True,
        "healthy": health["healthy"],
        "pid": pid,
        "container_port": port,
        "container_url": f"http://127.0.0.1:{port}/",
        "status_code": health.get("status_code"),
        "error": health.get("error"),
    }
    log_event("App runtime health result", {"container_id": container.id, "app": app})
    return app


def start_background_process(container, command: str, workdir: str) -> str:
    start_script = "\n".join(
        [
            f"cd {shlex.quote(workdir)}",
            f"nohup sh -lc {shlex.quote(command)} > {APP_LOG_PATH} 2>&1 &",
            f"echo $! > {APP_PID_PATH}",
            f"cat {APP_PID_PATH}",
        ]
    )
    result = exec_shell_or_raise(container, start_script)
    return result.stdout.strip().splitlines()[-1]


def wait_for_app_health(container, port: int, attempts: int = 45) -> dict[str, Any]:
    log_event(
        "Waiting for sandbox app health",
        {"container_id": container.id, "port": port, "attempts": attempts},
    )
    health_script = f"""
for i in $(seq 1 {attempts}); do
    code=$(curl -s -o /dev/null -w "%{{http_code}}" http://127.0.0.1:{port}/ || true)
    if [ "$code" != "000" ] && [ "$code" -lt 500 ]; then
        echo "$code"
        exit 0
    fi
    sleep 1
done
echo "app did not respond on port {port}"
tail -n 120 {APP_LOG_PATH} || true
exit 1
"""
    result = exec_shell(container, health_script)
    if result.ok:
        return {"healthy": True, "status_code": result.stdout.strip().splitlines()[-1]}

    return {
        "healthy": False,
        "error": f"{result.stdout.strip()}\n{result.stderr.strip()}".strip(),
    }


def attach_host_app_url(
    app: dict[str, Any],
    runtime: dict[str, Any],
    ports: dict[str, list[str]],
) -> None:
    port = runtime.get("port")
    if not port:
        return

    host_ports = ports.get(f"{port}/tcp") or []
    if host_ports:
        app["host_url"] = f"http://localhost:{host_ports[0]}/"
