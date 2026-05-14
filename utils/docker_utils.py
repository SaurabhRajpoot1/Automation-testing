"""Docker SDK helpers for sandbox orchestration."""

from dataclasses import dataclass
import io
import re
import tarfile
from typing import Any

from utils.logger import log_event


@dataclass
class DockerCommandResult:
    exit_code: int | None
    stdout: str
    stderr: str
    exec_id: str | None = None
    detached: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exec_id": self.exec_id,
            "detached": self.detached,
        }


def get_docker_client():
    try:
        import docker
    except ImportError as exc:
        raise RuntimeError("Docker SDK is not installed. Install the 'docker' package.") from exc

    return docker.from_env()


def get_container(container_id: str):
    client = get_docker_client()
    try:
        return client.containers.get(container_id)
    except Exception as exc:
        if exc.__class__.__name__ == "NotFound":
            raise RuntimeError(f"Container not found: {container_id}") from exc
        raise RuntimeError(f"Unable to load container {container_id}: {exc}") from exc


def ensure_container_running(container) -> None:
    container.reload()
    if container.status == "running":
        return

    log_event("Starting stopped sandbox container", {"container_id": container.id})
    container.start()
    container.reload()


def exec_command(
    container,
    command: list[str],
    workdir: str | None = None,
    environment: dict[str, str] | None = None,
    detach: bool = False,
) -> DockerCommandResult:
    log_event(
        "Executing command in sandbox",
        {
            "container_id": container.id,
            "command": redact_command(command),
            "workdir": workdir,
            "detach": detach,
        },
    )

    if detach:
        exec_info = container.client.api.exec_create(
            container.id,
            cmd=command,
            stdout=True,
            stderr=True,
            workdir=workdir,
            environment=environment,
        )
        exec_id = exec_info["Id"]
        container.client.api.exec_start(exec_id, detach=True)
        return DockerCommandResult(
            exit_code=None,
            stdout="",
            stderr="",
            exec_id=exec_id,
            detached=True,
        )

    result = container.exec_run(
        command,
        workdir=workdir,
        environment=environment,
        demux=True,
    )
    stdout_bytes, stderr_bytes = result.output or (b"", b"")

    return DockerCommandResult(
        exit_code=result.exit_code,
        stdout=decode_output(stdout_bytes),
        stderr=decode_output(stderr_bytes),
    )


def exec_shell(
    container,
    command: str,
    workdir: str | None = None,
    environment: dict[str, str] | None = None,
    detach: bool = False,
) -> DockerCommandResult:
    return exec_command(
        container,
        ["sh", "-lc", command],
        workdir=workdir,
        environment=environment,
        detach=detach,
    )


def exec_or_raise(
    container,
    command: list[str],
    workdir: str | None = None,
    environment: dict[str, str] | None = None,
) -> DockerCommandResult:
    result = exec_command(container, command, workdir=workdir, environment=environment)
    if result.ok:
        return result

    raise RuntimeError(
        f"Command failed with exit code {result.exit_code}: {' '.join(redact_command(command))}\n"
        f"stdout: {result.stdout.strip()}\n"
        f"stderr: {result.stderr.strip()}"
    )


def exec_shell_or_raise(
    container,
    command: str,
    workdir: str | None = None,
    environment: dict[str, str] | None = None,
) -> DockerCommandResult:
    result = exec_shell(container, command, workdir=workdir, environment=environment)
    if result.ok:
        return result

    raise RuntimeError(
        f"Command failed with exit code {result.exit_code}: {redact_secret(command)}\n"
        f"stdout: {result.stdout.strip()}\n"
        f"stderr: {result.stderr.strip()}"
    )


def put_text_file(container, path: str, content: str, mode: int = 0o644) -> None:
    directory, filename = split_container_path(path)
    exec_or_raise(container, ["mkdir", "-p", directory])

    data = content.encode("utf-8")
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(data)
        info.mode = mode
        tar.addfile(info, io.BytesIO(data))

    tar_stream.seek(0)
    container.put_archive(directory, tar_stream.read())


def read_text_file(container, path: str) -> str:
    result = exec_or_raise(container, ["cat", path])
    return result.stdout


def read_binary_file(container, path: str) -> bytes:
    archive_stream, _ = container.get_archive(path)
    tar_bytes = b"".join(archive_stream)
    tar_buffer = io.BytesIO(tar_bytes)

    with tarfile.open(fileobj=tar_buffer, mode="r:*") as tar:
        members = [member for member in tar.getmembers() if member.isfile()]
        if not members:
            raise RuntimeError(f"No file content found at container path: {path}")

        extracted = tar.extractfile(members[0])
        if extracted is None:
            raise RuntimeError(f"Unable to extract file from container path: {path}")

        return extracted.read()


def get_mapped_ports(container) -> dict[str, list[str]]:
    container.reload()
    ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    mapped_ports = {}

    for container_port, bindings in ports.items():
        if not bindings:
            continue
        mapped_ports[container_port] = [binding["HostPort"] for binding in bindings]

    return mapped_ports


def decode_output(output: bytes | None) -> str:
    if not output:
        return ""
    return output.decode("utf-8", errors="replace")


def redact_command(command: list[str]) -> list[str]:
    return [redact_secret(part) for part in command]


def redact_secret(value: str) -> str:
    return re.sub(r"(https://)[^:@\s]+:[^@\s]+@", r"\1***:***@", value)


def split_container_path(path: str) -> tuple[str, str]:
    normalized = path.rstrip("/")
    directory, _, filename = normalized.rpartition("/")
    if not directory or not filename:
        raise ValueError(f"Expected absolute file path, got: {path}")

    return directory, filename
