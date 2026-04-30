from fastapi import FastAPI, Request, Header, HTTPException
import requests
import os

app = FastAPI()

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

CMS_UPLOAD_URL = "https://ig.gov-cloud.ai/mobius-content-service/v1.0/content/upload?filePath=cms_pipeline"
CMS_TOKEN = os.getenv("CMS_TOKEN")


@app.post("/jira-webhook")
async def jira_webhook(
    request: Request,
    authorization: str = Header(None)
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON from Jira")

    # Optional: process only when status = AI Testing
    status = data.get("fields", {}).get("status", {}).get("name")
    if status != "AI Testing":
        return {"status": "ignored"}

    attachments = data.get("fields", {}).get("attachment", [])

    uploaded_files = []

    for att in attachments:
        url = att.get("content")
        filename = att.get("filename")

        if not url or not filename:
            continue

        # Step 1: Stream download from Jira
        jira_response = requests.get(
            url,
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            stream=True
        )

        if jira_response.status_code != 200:
            uploaded_files.append({
                "file": filename,
                "error": "Failed to download from Jira"
            })
            continue

        # Step 2: Direct upload to CMS (NO local file)
        files = {
            "file": (filename, jira_response.raw)
        }

        headers = {
            "Authorization": f"Bearer {CMS_TOKEN}"
        }

        cms_response = requests.post(
            CMS_UPLOAD_URL,
            headers=headers,
            files=files
        )

        if cms_response.status_code == 200:
            uploaded_files.append(cms_response.json())
        else:
            uploaded_files.append({
                "file": filename,
                "error": cms_response.text
            })

    return {
        "status": "processed",
        "uploaded_count": len(uploaded_files),
        "results": uploaded_files
    }