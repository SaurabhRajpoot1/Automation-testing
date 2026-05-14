from fastapi import APIRouter

from core.logging import log

router = APIRouter()


@router.get("/")
def health() -> dict[str, str]:
    log("Health check called")
    return {"status": "ok"}
