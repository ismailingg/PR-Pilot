import hmac
import hashlib
import os
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

# Import the manager we just created
from prtool.utils.github_manager import GitHubManager

load_dotenv()
app = FastAPI()

@app.post("/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    # 1. SECURITY: Get raw body and verify the signature
    payload = await request.body()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret missing in .env")

    # Re-hash the message to see if it matches GitHub's signature
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    if not x_hub_signature_256 or not hmac.compare_digest(signature, x_hub_signature_256):
        print("❌ SECURITY ALERT: Unauthorized signature attempted!")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. DATA PARSING
    data = await request.json()
    action = data.get("action")
    
    # We only care if a PR is opened or updated with new code
    if action in ["opened", "synchronize", "ready_for_review"]:
        repo_name = data["repository"]["full_name"]
        pr_num = data["pull_request"]["number"]
        install_id = data["installation"]["id"]
        
        try:
            # 3. LIVE FETCH: Reach back to GitHub for the actual diff
            gh = GitHubManager(install_id)
            details = gh.get_pr_details(repo_name, pr_num)
            
            print(f"\n🔍 [LIVE AUDIT INITIALIZED]")
            print(f"📦 Repo: {repo_name}")
            print(f"📝 PR: {details['title']}")
            print(f"✂️ Diff Snippet (First 200 chars):\n{details['diff'][:200]}...")
            print("-" * 40)
            
            # TODO: In the next step, we will pass 'details' to your CrewAI agents!
            
        except Exception as e:
            print(f"❌ Error fetching PR details: {str(e)}")

    return {"status": "accepted"}

@app.get("/")
async def root():
    return {"message": "MergeMate Auditor API is Online!"}