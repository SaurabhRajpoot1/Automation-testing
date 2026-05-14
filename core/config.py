"""Application configuration helpers."""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def load_env_file() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    jira_email: str | None
    jira_api_token: str | None
    github_token: str | None
    cloudinary_cloud_name: str | None
    cloudinary_api_key: str | None
    cloudinary_api_secret: str | None
    cloudinary_folder: str
    pr_files_dir: str
    github_api_base_url: str

    @property
    def has_jira_credentials(self) -> bool:
        return bool(self.jira_email and self.jira_api_token)


@lru_cache
def get_settings() -> Settings:
    load_env_file()
    return Settings(
        jira_email=os.getenv("JIRA_EMAIL"),
        jira_api_token=os.getenv("JIRA_API_TOKEN"),
        github_token=os.getenv("GITHUB_TOKEN"),
        cloudinary_cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        cloudinary_api_key=os.getenv("CLOUDINARY_API_KEY"),
        cloudinary_api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        cloudinary_folder=os.getenv("CLOUDINARY_FOLDER", "jira-uploads"),
        pr_files_dir=os.getenv("PR_FILES_DIR", "storage/pr_files"),
        github_api_base_url=os.getenv("GITHUB_API_BASE_URL", "https://api.github.com"),
    )
