import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    data = await request.json()

    attachments = data.get("fields", {}).get("attachment", [])

    for att in attachments:
        url = att["content"]
        filename = att["filename"]

        response = requests.get(
            url,
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            stream=True
        )

        if response.status_code == 200:
            with open(f"downloads/{filename}", "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)

    return {"status": "done"}