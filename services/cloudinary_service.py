"""Cloudinary upload logic."""

import cloudinary
import cloudinary.uploader

from core.config import Settings, get_settings
from core.logging import log


def configure_cloudinary(settings: Settings | None = None) -> None:
    settings = settings or get_settings()

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
    )


def upload_to_cloudinary(
    file_bytes: bytes,
    filename: str | None,
    settings: Settings | None = None,
    *,
    folder: str | None = None,
    resource_type: str = "auto",
) -> dict[str, str | None]:
    settings = settings or get_settings()
    configure_cloudinary(settings)

    log("Uploading to Cloudinary", {"filename": filename, "size": len(file_bytes)})

    result = cloudinary.uploader.upload(
        file_bytes,
        resource_type=resource_type,
        folder=folder or settings.cloudinary_folder,
    )

    upload_result = {
        "url": result.get("secure_url"),
        "public_id": result.get("public_id"),
        "resource_type": result.get("resource_type"),
    }
    log("Cloudinary upload completed", upload_result)

    return upload_result
