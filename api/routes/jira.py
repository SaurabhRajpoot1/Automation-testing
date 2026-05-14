from fastapi import APIRouter, Depends

from api.deps import get_app_settings
from core.config import Settings
from core.logging import log
from models.jira_models import JiraWebhookPayload, JiraWebhookResponse
from services.jira_service import process_jira_webhook

router = APIRouter(tags=["jira"])


@router.post("/jira-webhook", response_model=JiraWebhookResponse)
async def jira_webhook(
    payload: JiraWebhookPayload,
    settings: Settings = Depends(get_app_settings),
) -> dict:
    log("Jira webhook received")

    if hasattr(payload, "model_dump"):
        payload_data = payload.model_dump()
    else:
        payload_data = payload.dict()

    return process_jira_webhook(payload_data, settings)
