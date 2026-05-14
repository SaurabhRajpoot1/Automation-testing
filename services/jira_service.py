"""Jira business logic."""

from typing import Any

import requests

from core.config import Settings, get_settings
from core.logging import log
from services.cloudinary_service import upload_to_cloudinary


def process_jira_webhook(
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()

    issue_key = payload.get("issue_key")
    status = payload.get("status")
    summary = payload.get("summary")
    attachments = payload.get("attachments") or []
    comments = payload.get("comments") or []

    log(
        "Processing Jira webhook",
        {
            "issue": issue_key,
            "status": status,
            "summary": summary,
            "attachments": len(attachments),
            "comments": len(comments),
        },
    )

    results = [
        process_attachment(attachment, settings)
        for attachment in attachments
        if isinstance(attachment, dict)
    ]

    for comment in comments:
        if isinstance(comment, dict):
            log(
                "Jira comment received",
                {
                    "author": comment.get("author"),
                    "body": comment.get("body"),
                },
            )

    return {
        "issue": issue_key,
        "status": status,
        "processed_files": len(results),
        "results": results,
        "comments_received": len(comments),
    }


def process_attachment(
    attachment: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    url = attachment.get("url")
    filename = attachment.get("filename")

    log("Processing Jira attachment", {"filename": filename, "url": url})

    if not url:
        return {"file": filename, "error": "No URL found"}

    if not settings.has_jira_credentials:
        return {"file": filename, "error": "Jira credentials are not configured"}

    try:
        response = requests.get(
            url,
            auth=(settings.jira_email, settings.jira_api_token),
            timeout=20,
        )
    except requests.RequestException as exc:
        log("Jira attachment download failed", {"filename": filename, "error": str(exc)})
        return {"file": filename, "error": str(exc)}

    if response.status_code != 200:
        return {
            "file": filename,
            "error": "Download failed",
            "status_code": response.status_code,
        }

    try:
        upload_result = upload_to_cloudinary(response.content, filename, settings)
    except Exception as exc:
        log("Cloudinary upload failed", {"filename": filename, "error": str(exc)})
        return {"file": filename, "error": str(exc)}

    return {"file": filename, "cloudinary": upload_result}
