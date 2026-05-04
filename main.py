from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import requests
import os
import cloudinary
import cloudinary.uploader

app = FastAPI()

# -------------------------------
# ENV CONFIG
# -------------------------------
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

CMS_UPLOAD_URL = "https://ig.gov-cloud.ai/mobius-content-service/v1.0/content/upload?filePath=cms_pipeline"
CMS_TOKEN = os.getenv("CMS_TOKEN")

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)


# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.get("/")
def health():
    return {"status": "ok"}


# -------------------------------
# CMS TEST ENDPOINT
# -------------------------------
@app.post("/upload-to-cms")
async def upload_to_cms(file: UploadFile = File(...)):
    try:
        file_content = await file.read()

        files = {
            "file": (file.filename, file_content, file.content_type)
        }

        headers = {
            "Authorization": f"Bearer {CMS_TOKEN}"
        }

        response = requests.post(
            CMS_UPLOAD_URL,
            headers=headers,
            files=files,
            timeout=10
        )

        return {
            "cms_status_code": response.status_code,
            "cms_response": response.text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------
# CLOUDINARY FALLBACK
# -------------------------------
def upload_to_cloudinary(file_bytes, filename):
    result = cloudinary.uploader.upload(
        file_bytes,
        resource_type="auto",
        folder="jira-uploads"
    )
    return {
        "url": result.get("secure_url"),
        "public_id": result.get("public_id")
    }


# -------------------------------
# JIRA WEBHOOK
# -------------------------------
@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON from Jira")

    # ✅ Correct parsing
    issue = data.get("issue", {})
    fields = issue.get("fields", {})

    status = fields.get("status", {}).get("name")
    issue_key = issue.get("key")

    if status != "AI Testing":
        return {"status": "ignored"}

    attachments = fields.get("attachment", [])
    results = []

    for att in attachments:
        url = att.get("content")
        filename = att.get("filename")

        if not url:
            continue

        try:
            # -------------------------------
            # 1. Download from Jira
            # -------------------------------
            jira_response = requests.get(
                url,
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                timeout=10
            )

            if jira_response.status_code != 200:
                results.append({
                    "file": filename,
                    "error": "Download failed"
                })
                continue

            file_bytes = jira_response.content

            # -------------------------------
            # 2. Try CMS upload
            # -------------------------------
            try:
                files = {
                    "file": (filename, file_bytes)
                }

                headers = {
                    "Authorization": f"Bearer {CMS_TOKEN}"
                }

                cms_response = requests.post(
                    CMS_UPLOAD_URL,
                    headers=headers,
                    files=files,
                    timeout=10
                )

                if cms_response.status_code == 200:
                    results.append({
                        "file": filename,
                        "cms": cms_response.json()
                    })
                    continue

                else:
                    print(f"⚠️ CMS failed: {cms_response.text}")

            except Exception as cms_error:
                print(f"⚠️ CMS exception: {cms_error}")

            # -------------------------------
            # 3. Fallback → Cloudinary
            # -------------------------------
            cloudinary_result = upload_to_cloudinary(file_bytes, filename)

            results.append({
                "file": filename,
                "cloudinary": cloudinary_result
            })

        except Exception as e:
            results.append({
                "file": filename,
                "error": str(e)
            })

    return {
        "issue": issue_key,
        "processed_files": len(results),
        "results": results
    }