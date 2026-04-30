from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

@app.post("/jira-webhook")
async def jira_webhook(request: Request):
    data = await request.json()

    # Log everything (very important for debugging Jira payloads)
    print("Received Jira Event:")
    print(data)

    return JSONResponse({
        "status": "success",
        "message": "Webhook received",
        "received_keys": list(data.keys())
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)