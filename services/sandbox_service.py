"""Docker sandbox creation."""

import re
from typing import Any
from uuid import uuid4

from core.config import Settings, get_settings
from services.github_service import parse_github_pr_url
from services.sandbox_constants import (
    GENERATED_TESTS_PATH,
    REPO_PATH,
    SANDBOX_BASE_IMAGE,
    SANDBOX_PORTS,
    SANDBOX_WORKDIR,
)
from utils.docker_utils import (
    exec_or_raise,
    get_docker_client,
    get_mapped_ports,
)
from utils.logger import log_event


def create_sandbox(
    pr_url: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()

    parsed = parse_github_pr_url(pr_url)

    if not parsed:
        return {"error": "Invalid PR URL"}

    owner, repo, pr_number = parsed

    public_repo_url = f"https://github.com/{owner}/{repo}.git"

    clone_url = build_clone_url(owner, repo, settings)

    sandbox_id = build_sandbox_id(owner, repo, pr_number)

    try:
        docker_client = get_docker_client()

        container = run_sandbox_container(
            docker_client=docker_client,
            sandbox_id=sandbox_id,
        )

        log_event(
            "Sandbox container created",
            {
                "container_id": container.id,
                "sandbox_id": sandbox_id,
                "image": SANDBOX_BASE_IMAGE,
            },
        )

        # ---------------------------------------------------
        # Validate runtime
        # ---------------------------------------------------
        validate_runtime(container)

        # ---------------------------------------------------
        # Clone repository
        # ---------------------------------------------------
        clone_pull_request(
            container=container,
            clone_url=clone_url,
            public_repo_url=public_repo_url,
            pr_number=pr_number,
        )

        # ---------------------------------------------------
        # Ensure tests folder
        # ---------------------------------------------------
        create_generated_tests_folder(container)

        ports = get_mapped_ports(container)

        log_event(
            "Sandbox repository ready",
            {
                "container_id": container.id,
                "repo_path": REPO_PATH,
                "tests_path": GENERATED_TESTS_PATH,
                "ports": ports,
            },
        )

        return {
            "container_id": container.id,
            "image": SANDBOX_BASE_IMAGE,
            "sandbox_id": sandbox_id,
            "repo_path": REPO_PATH,
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "tests_path": GENERATED_TESTS_PATH,
            "ports": ports,
            "status": "sandbox ready",
        }

    except Exception as exc:
        log_event(
            "Sandbox creation failed",
            {
                "error": str(exc),
            },
        )

        return {
            "error": str(exc),
        }


def build_sandbox_id(
    owner: str,
    repo: str,
    pr_number: str,
) -> str:
    raw_id = f"{owner}-{repo}-pr-{pr_number}-{uuid4().hex[:8]}".lower()

    return re.sub(r"[^a-z0-9_.-]+", "-", raw_id).strip("-")


def build_clone_url(
    owner: str,
    repo: str,
    settings: Settings,
) -> str:
    if not settings.github_token:
        return f"https://github.com/{owner}/{repo}.git"

    return (
        f"https://x-access-token:"
        f"{settings.github_token}"
        f"@github.com/{owner}/{repo}.git"
    )


def run_sandbox_container(
    docker_client,
    sandbox_id: str,
):
    log_event(
        "Creating sandbox container",
        {
            "sandbox_id": sandbox_id,
            "image": SANDBOX_BASE_IMAGE,
        },
    )

    # ---------------------------------------------------
    # Always pull latest image
    # ---------------------------------------------------
    docker_client.images.pull(SANDBOX_BASE_IMAGE)

    container = docker_client.containers.run(
        SANDBOX_BASE_IMAGE,
        command=["sleep", "infinity"],
        detach=True,
        tty=True,
        working_dir=SANDBOX_WORKDIR,
        ports={port: None for port in SANDBOX_PORTS},
        name=f"sandbox-{sandbox_id}",
        labels={
            "automation-testing.sandbox": "true",
            "automation-testing.sandbox_id": sandbox_id,
        },
    )

    return container


def validate_runtime(container) -> None:
    """
    Ensure node/npm/npx/git exist inside sandbox.
    """

    log_event(
        "Validating sandbox runtime",
        {
            "container_id": container.id,
        },
    )

    node_version = exec_or_raise(container, ["node", "-v"])
    npm_version = exec_or_raise(container, ["npm", "-v"])
    npx_version = exec_or_raise(container, ["npx", "-v"])
    git_version = exec_or_raise(container, ["git", "--version"])

    log_event(
        "Sandbox runtime validated",
        {
            "container_id": container.id,
            "node": node_version,
            "npm": npm_version,
            "npx": npx_version,
            "git": git_version,
        },
    )


def clone_pull_request(
    container,
    clone_url: str,
    public_repo_url: str,
    pr_number: str,
) -> None:
    log_event(
        "Cloning repository into sandbox",
        {
            "container_id": container.id,
        },
    )

    exec_or_raise(
        container,
        [
            "git",
            "clone",
            "--no-tags",
            clone_url,
            REPO_PATH,
        ],
    )

    exec_or_raise(
        container,
        [
            "git",
            "fetch",
            "origin",
            f"pull/{pr_number}/head:pr_branch",
        ],
        workdir=REPO_PATH,
    )

    exec_or_raise(
        container,
        [
            "git",
            "checkout",
            "pr_branch",
        ],
        workdir=REPO_PATH,
    )

    # ---------------------------------------------------
    # Reset origin to public URL
    # ---------------------------------------------------
    exec_or_raise(
        container,
        [
            "git",
            "remote",
            "set-url",
            "origin",
            public_repo_url,
        ],
        workdir=REPO_PATH,
    )

    log_event(
        "Repository checkout complete",
        {
            "container_id": container.id,
            "pr_number": pr_number,
        },
    )


def create_generated_tests_folder(container) -> None:
    exec_or_raise(
        container,
        [
            "mkdir",
            "-p",
            GENERATED_TESTS_PATH,
        ],
    )

    log_event(
        "Generated tests folder ensured",
        {
            "container_id": container.id,
            "path": GENERATED_TESTS_PATH,
        },
    )