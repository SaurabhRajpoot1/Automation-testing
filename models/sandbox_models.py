"""Sandbox request and response schemas."""

from pydantic import BaseModel


class SandboxRequest(BaseModel):
    pr_url: str


class BootstrapSandboxRequest(BaseModel):
    container_id: str


class ExecuteInSandboxRequest(BaseModel):
    container_id: str
    command: str
    workdir: str | None = None
    detach: bool = False


class GeneratedTestFile(BaseModel):
    name: str
    content: str


class GenerateTestFolderRequest(BaseModel):
    container_id: str
    files: list[GeneratedTestFile]


class RunPlaywrightTestsRequest(BaseModel):
    container_id: str
