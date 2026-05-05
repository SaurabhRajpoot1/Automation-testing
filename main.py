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
@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    print("\n🚀 JIRA WEBHOOK HIT", flush=True)

    try:
        raw_body = await request.body()
        body_str = raw_body.decode("utf-8")
        print("📦 RAW BODY:", body_str, flush=True)

        data = json.loads(body_str)

    except Exception as e:
        print("❌ JSON PARSE ERROR:", str(e), flush=True)
        return {"error": "invalid json"}

    # ✅ PARSE YOUR CUSTOM PAYLOAD
    issue_key = data.get("issue_key")
    status = data.get("status")
    summary = data.get("summary")

    attachments = data.get("attachments", [])
    comments = data.get("comments", [])

    print(f"✅ Issue: {issue_key}", flush=True)
    print(f"📌 Status: {status}", flush=True)
    print(f"📝 Summary: {summary}", flush=True)
    print(f"📎 Attachments: {len(attachments)}", flush=True)
    print(f"💬 Comments: {len(comments)}", flush=True)

    results = []

    # -------------------------------
    # PROCESS ATTACHMENTS
    # -------------------------------
    for att in attachments:
        url = att.get("url")        # ✅ your payload uses "url"
        filename = att.get("filename")

        print(f"\n⬇️ Processing file: {filename}", flush=True)
        print(f"🔗 URL: {url}", flush=True)

        if not url:
            print("⚠️ No URL found, skipping", flush=True)
            continue

        try:
            jira_response = requests.get(
                url,
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                timeout=20
            )

            print(f"📥 Jira response: {jira_response.status_code}", flush=True)

            if jira_response.status_code != 200:
                results.append({
                    "file": filename,
                    "error": "Download failed"
                })
                continue

            file_bytes = jira_response.content

            # ✅ USE YOUR HELPER (cleaner)
            upload_result = upload_to_cloudinary(file_bytes, filename)

            results.append({
                "file": filename,
                "cloudinary": upload_result
            })

        except Exception as e:
            print(f"❌ ERROR: {str(e)}", flush=True)
            results.append({
                "file": filename,
                "error": str(e)
            })

    # -------------------------------
    # LOG COMMENTS (optional)
    # -------------------------------
    for c in comments:
        print(f"\n💬 Comment by {c.get('author')}", flush=True)
        print(f"📝 {c.get('body')}", flush=True)

    final_response = {
        "issue": issue_key,
        "status": status,
        "processed_files": len(results),
        "results": results,
        "comments_received": len(comments)
    }

    print("\n✅ FINAL RESPONSE:", final_response, flush=True)

    return final_response