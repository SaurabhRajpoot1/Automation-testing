"""GitHub business logic."""

from pathlib import Path
import re
from typing import Any

import requests

from core.config import Settings, get_settings
from core.logging import log

PR_URL_PATTERN = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def parse_github_pr_url(pr_url: str) -> tuple[str, str, str] | None:
    match = PR_URL_PATTERN.search(pr_url)
    if not match:
        return None

    return match.group(1), match.group(2), match.group(3)


def get_github_pr_files(
    pr_url: str,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    settings = settings or get_settings()
    parsed = parse_github_pr_url(pr_url)
    if not parsed:
        return None, "Invalid PR URL"

    owner, repo, pull_number = parsed
    url = f"{settings.github_api_base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"

    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException as exc:
        return None, str(exc)

    if response.status_code != 200:
        return None, response.text

    return response.json(), None


def save_pr_patches(
    files: list[dict[str, Any]],
    save_dir: str,
) -> list[dict[str, str]]:
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file_info in files:
        filename = file_info.get("filename")
        patch = file_info.get("patch")

        if not filename or not patch:
            log("Skipping PR file without patch", {"filename": filename})
            continue

        safe_filename = filename.replace("/", "_")
        file_path = save_path / f"{safe_filename}.diff"
        file_path.write_text(patch, encoding="utf-8")

        log("Saved PR patch", {"file_path": str(file_path)})
        saved_files.append(
            {
                "original": filename,
                "saved_as": str(file_path),
            }
        )

    return saved_files


def process_github_pr(
    pr_url: str,
    settings: Settings | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    settings = settings or get_settings()

    files, error = get_github_pr_files(pr_url, settings)
    if error:
        return None, error

    saved_files = save_pr_patches(files or [], settings.pr_files_dir)
    return (
        {
            "message": "PR processed successfully",
            "total_files": len(saved_files),
            "saved_files": saved_files,
        },
        None,
    )
