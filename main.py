import os
import requests
from fastapi import FastAPI, Request
from requests.auth import HTTPBasicAuth
app = FastAPI()

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

@app.get("/files")
async def list_files():
    files = os.listdir("downloads") if os.path.exists("downloads") else []
    return {"files": files}
@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        body = await request.body()
        print("Invalid JSON received:", body)
        return {"status": "ignored - invalid json"}

    print("Received Jira Event")

    # ✅ Optional: filter only AI Testing status
    status = data.get("fields", {}).get("status", {}).get("name")
    if status != "AI Testing":
        return {"status": f"ignored - status is {status}"}

    # ✅ Ensure directory exists (fix for Render error)
    os.makedirs("downloads", exist_ok=True)

    attachments = data.get("fields", {}).get("attachment", [])

    if not attachments:
        print("No attachments found")
        return {"status": "no attachments"}

    for att in attachments:
        url = att.get("content")
        filename = att.get("filename")

        if not url or not filename:
            continue

        print(f"Downloading: {filename}")

        try:
            response = requests.get(
                url,
                auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                stream=True,
                timeout=20
            )

            if response.status_code == 200:
                file_path = f"downloads/{filename}"

                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)

                size = os.path.getsize(file_path)
                print(f"Saved: {filename} ({size} bytes)")
            else:
                print(f"Failed: {filename}, status={response.status_code}")

        except Exception as e:
            print(f"Error downloading {filename}: {e}")

    return {"status": "processed"}