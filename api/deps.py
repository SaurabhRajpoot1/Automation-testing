"""Shared API dependencies."""

from core.config import Settings, get_settings


def get_app_settings() -> Settings:
    return get_settings()
