from fastapi import APIRouter, HTTPException

from models.sandbox_models import (
    BootstrapSandboxRequest,
    ExecuteInSandboxRequest,
    SandboxRequest,
)
from services.bootstrap_service import bootstrap_sandbox
from services.execution_service import execute_in_sandbox
from services.sandbox_service import create_sandbox

router = APIRouter(tags=["sandbox"])


@router.post("/create-sandbox")
def create_sandbox_api(req: SandboxRequest) -> dict:
    result = create_sandbox(req.pr_url)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/bootstrap-sandbox")
def bootstrap_sandbox_api(req: BootstrapSandboxRequest) -> dict:
    result = bootstrap_sandbox(req.container_id)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/execute-in-sandbox")
def execute_in_sandbox_api(req: ExecuteInSandboxRequest) -> dict:
    result = execute_in_sandbox(
        req.container_id,
        req.command,
        workdir=req.workdir,
        detach=req.detach,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
