from fastapi import APIRouter, HTTPException

from models.sandbox_models import GenerateTestFolderRequest, RunPlaywrightTestsRequest
from services.playwright_service import generate_test_folder, run_playwright_tests

router = APIRouter(tags=["tests"])


@router.post("/generate-test-folder")
def generate_test_folder_api(req: GenerateTestFolderRequest) -> dict:
    result = generate_test_folder(
        req.container_id,
        [dump_model(file) for file in req.files],
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/run-playwright-tests")
def run_playwright_tests_api(req: RunPlaywrightTestsRequest) -> dict:
    result = run_playwright_tests(req.container_id)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


def dump_model(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
