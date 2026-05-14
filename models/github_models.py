"""GitHub request and response schemas."""

from pydantic import BaseModel, Field


class SavedPrFile(BaseModel):
    original: str
    saved_as: str


class GithubPrProcessResponse(BaseModel):
    message: str
    total_files: int
    saved_files: list[SavedPrFile] = Field(default_factory=list)
