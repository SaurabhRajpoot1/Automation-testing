from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_app_settings
from core.config import Settings
from core.logging import log
from models.github_models import GithubPrProcessResponse
from services.github_service import process_github_pr

router = APIRouter(tags=["github"])


@router.get("/test-github-pr", response_model=GithubPrProcessResponse)
def test_github_pr(
    pr_url: str = Query(...),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    log("Testing GitHub PR", {"pr_url": pr_url})

    response, error = process_github_pr(pr_url, settings)
    if error:
        log("GitHub PR processing failed", {"error": error})
        raise HTTPException(status_code=400, detail=error)

    return response
