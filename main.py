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
    print("\n🚀 JIRA WEBHOOK HIT")

    try:
        data = await request.json()
        print("📦 RAW PAYLOAD RECEIVED")
    except Exception as e:
        print("❌ Invalid JSON:", str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # ✅ Correct extraction
    issue = data.get("issue", {})
    fields = issue.get("fields", {})

    issue_key = issue.get("key")
    status = fields.get("status", {}).get("name")

    print(f"✅ Issue Key: {issue_key}")
    print(f"✅ Status: {status}")

    # 🚨 IMPORTANT FIX: handle None safely
    if not status or status.strip() != "AI Testing":
        print("⛔ Status not AI Testing, ignoring")
        return {"status": "ignored"}

    attachments = fields.get("attachment", [])

    print(f"📎 Total attachments: {len(attachments)}")

    results = []

    for att in attachments:
        url = att.get("content")
        filename = att.get("filename")

        print(f"\n⬇️ Processing file: {filename}")
        print(f"🔗 URL: {url}")

        if not url:
            print("⚠️ No URL found, skipping")
            continue

        try:
            # -------------------------------
            # DOWNLOAD FROM JIRA
            # -------------------------------
            jira_response = requests.get(
                url,
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                timeout=20
            )

            print(f"📥 Jira response: {jira_response.status_code}")

            if jira_response.status_code != 200:
                print("❌ Download failed")
                results.append({
                    "file": filename,
                    "error": "Download failed"
                })
                continue

            file_bytes = jira_response.content

            print(f"📦 File size: {len(file_bytes)} bytes")

            # -------------------------------
            # UPLOAD TO CLOUDINARY
            # -------------------------------
            upload_result = cloudinary.uploader.upload(
                file_bytes,
                resource_type="auto",
                folder="jira-uploads"
            )

            print("☁️ Uploaded to Cloudinary")

            results.append({
                "file": filename,
                "url": upload_result.get("secure_url"),
                "public_id": upload_result.get("public_id")
            })

        except Exception as e:
            print(f"❌ ERROR processing file: {str(e)}")
            results.append({
                "file": filename,
                "error": str(e)
            })

    final_response = {
        "issue": issue_key,
        "processed_files": len(results),
        "results": results
    }

    print("\n✅ FINAL RESPONSE:", final_response)

    return final_response