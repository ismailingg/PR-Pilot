import hmac
import hashlib
import os
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

# --- NEW IMPORTS ---
from prtool.utils.github_manager import GitHubManager
from prtool.crew import PrToolCrew  # This is your agent file!

load_dotenv()
app = FastAPI()

@app.post("/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    payload = await request.body()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    
    # 1. Security Check (Keep this!)
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    action = data.get("action")
    
    if action in ["opened", "synchronize"]:
        repo_name = data["repository"]["full_name"]
        pr_num = data["pull_request"]["number"]
        install_id = data["installation"]["id"]
        
        # 2. Fetch the live data
        gh = GitHubManager(install_id)
        details = gh.get_pr_details(repo_name, pr_num)
        
        print(f" [AUDIT STARTING] PR #{pr_num}: {details['title']}")

        # 3. KICKOFF THE CREW
        # We pass the real data into the inputs dictionary
        inputs = {
            "diff": details["diff"],
            "pr_body": details["body"],
            "issue_description": "Still fetched from local for now, or link a URL...", 
            "repo_context": repo_name
        }

        # This runs your agents!
        result = PrToolCrew().crew().kickoff(inputs=inputs)

        print("\n [AUDIT COMPLETE]")
        print(result.raw) # This will print the AI's final verdict to your console

    return {"status": "accepted"}