"""Jira request and response schemas."""

from pydantic import BaseModel, Field


class JiraAttachment(BaseModel):
    url: str | None = None
    filename: str | None = None


class JiraComment(BaseModel):
    author: str | None = None
    body: str | None = None


class JiraWebhookPayload(BaseModel):
    issue_key: str | None = None
    status: str | None = None
    summary: str | None = None
    attachments: list[JiraAttachment] = Field(default_factory=list)
    comments: list[JiraComment] = Field(default_factory=list)


class CloudinaryUploadResult(BaseModel):
    url: str | None = None
    public_id: str | None = None
    resource_type: str | None = None


class JiraAttachmentResult(BaseModel):
    file: str | None = None
    cloudinary: CloudinaryUploadResult | None = None
    error: str | None = None
    status_code: int | None = None


class JiraWebhookResponse(BaseModel):
    issue: str | None = None
    status: str | None = None
    processed_files: int
    results: list[JiraAttachmentResult] = Field(default_factory=list)
    comments_received: int
