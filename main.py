from fastapi import FastAPI, Request, UploadFile, File, HTTPException
import requests
import os
import cloudinary
import cloudinary.uploader
import json

app = FastAPI()

# -------------------------------
# ENV CONFIG
# -------------------------------
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

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
# CLOUDINARY UPLOAD FUNCTION
# -------------------------------
def upload_to_cloudinary(file_bytes, filename):
    result = cloudinary.uploader.upload(
        file_bytes,
        resource_type="auto",
        folder="jira-uploads"
    )
    print(json.dumps(result))
    return {
        "url": result.get("secure_url"),
        "public_id": result.get("public_id"),
        "resource_type": result.get("resource_type")
    }


# -------------------------------
# DIRECT UPLOAD ENDPOINT (for testing)
# -------------------------------
@app.post("/upload-to-cloudinary-new")
async def upload_to_cloudinary_api(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()

        result = upload_to_cloudinary(file_bytes, file.filename)

        return {
            "message": "Upload successful ✅",
            "data": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------
# JIRA WEBHOOK
# -------------------------------
@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON from Jira")

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
            # 2. Upload to Cloudinary
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

    data = {
        "issue": issue_key,
        "processed_files": len(results),
        "results": results
    }
    
    print(json.dumps(data))

    return data