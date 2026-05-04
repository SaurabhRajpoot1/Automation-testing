from fastapi import FastAPI, Request, UploadFile, File, HTTPException
import requests
import os
import cloudinary
import cloudinary.uploader
import json
from requests.auth import HTTPBasicAuth
from datetime import datetime

app = FastAPI()

# -------------------------------
# ENV CONFIG
# -------------------------------
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

# -------------------------------
# HELPER LOG FUNCTION (IMPORTANT)
# -------------------------------
def log(message, data=None):
    log_data = {
        "time": str(datetime.utcnow()),
        "message": message,
        "data": data
    }
    print(json.dumps(log_data), flush=True)  # flush=True is key for Render


# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.get("/")
def health():
    log("Health check called")
    return {"status": "ok"}


# -------------------------------
# CLOUDINARY UPLOAD
# -------------------------------
def upload_to_cloudinary(file_bytes, filename):
    log("Uploading to Cloudinary", {"filename": filename, "size": len(file_bytes)})

    result = cloudinary.uploader.upload(
        file_bytes,
        resource_type="auto",
        folder="jira-uploads"
    )

    log("Cloudinary success", result)

    return {
        "url": result.get("secure_url"),
        "public_id": result.get("public_id"),
        "resource_type": result.get("resource_type")
    }


# -------------------------------
# TEST ENDPOINT
# -------------------------------
@app.post("/upload-to-cloudinary-new")
async def upload_to_cloudinary_api(file: UploadFile = File(...)):
    log("Direct upload endpoint hit")

    try:
        file_bytes = await file.read()
        result = upload_to_cloudinary(file_bytes, file.filename)

        return {"message": "Upload successful", "data": result}

    except Exception as e:
        log("Direct upload error", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------
# JIRA WEBHOOK
# -------------------------------
@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    log("🚀 JIRA WEBHOOK HIT")

    try:
        data = await request.json()
        log("Received Jira payload", data)
    except Exception as e:
        log("Invalid JSON", str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")

    issue = data.get("issue", {})
    fields = issue.get("fields", {})

    status = fields.get("status", {}).get("name")
    issue_key = issue.get("key")

    log("Parsed issue", {"issue_key": issue_key, "status": status})

    if status != "AI Testing":
        log("Status not AI Testing, ignoring")
        return {"status": "ignored"}

    attachments = fields.get("attachment", [])
    log("Attachments found", attachments)

    results = []

    for att in attachments:
        url = att.get("content")
        filename = att.get("filename")

        log("Processing attachment", {"filename": filename, "url": url})

        if not url:
            continue

        try:
            # -------------------------------
            # Download from Jira
            # -------------------------------
            jira_response = requests.get(
                url,
                auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
                headers={"Accept": "application/octet-stream"},
                timeout=10
            )

            log("Jira response", {
                "status": jira_response.status_code,
                "content_type": jira_response.headers.get("Content-Type"),
                "size": len(jira_response.content)
            })

            if jira_response.status_code != 200:
                results.append({"file": filename, "error": "Download failed"})
                continue

            file_bytes = jira_response.content

            if len(file_bytes) < 100:
                log("⚠️ File too small, likely auth issue")
                results.append({"file": filename, "error": "Invalid file"})
                continue

            # -------------------------------
            # Upload to Cloudinary
            # -------------------------------
            cloudinary_result = upload_to_cloudinary(file_bytes, filename)

            results.append({
                "file": filename,
                "cloudinary": cloudinary_result
            })

        except Exception as e:
            log("Error processing file", str(e))
            results.append({
                "file": filename,
                "error": str(e)
            })

    final_data = {
        "issue": issue_key,
        "processed_files": len(results),
        "results": results
    }

    log("Final response", final_data)

    return final_data