# src/prtool/api.py
import hmac
import hashlib
import os
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

# Load your .env secrets
load_dotenv()

app = FastAPI()

@app.post("/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    # 1. Get the raw body of the message
    payload = await request.body()
    
    # 2. Security Check: Verify the signature from GitHub
    # This ensures the message actually came from YOUR GitHub App
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured in .env")
        
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    if not x_hub_signature_256 or not hmac.compare_digest(signature, x_hub_signature_256):
        print(" Security Alert: Invalid Webhook Signature!")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Parse the JSON data
    data = await request.json()
    action = data.get("action")
    pr_info = data.get("pull_request", {})
    repo_name = data.get("repository", {}).get("full_name")
    
    print(f"\n [GITHUB EVENT] {repo_name}")
    print(f" Action: {action}")
    print(f" PR Title: {pr_info.get('title')}")
    print("-" * 30)

    return {"status": "accepted"}

@app.get("/")
async def root():
    return {"message": "MergeMate API is Online!"}