import hmac
import hashlib
import os
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

# Imports for your logic
from prtool.utils.github_manager import GitHubManager
from prtool.crew import PrToolCrew

load_dotenv()
app = FastAPI()

@app.post("/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    payload = await request.body()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    
    # 1. Signature Verification
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    action = data.get("action")
    
    # Trigger only on PR creation or new code pushes
    if action in ["opened", "synchronize"]:
        repo_name = data["repository"]["full_name"]
        pr_num = data["pull_request"]["number"]
        install_id = data["installation"]["id"]
        
        # 2. Fetch live PR details
        gh = GitHubManager(install_id)
        details = gh.get_pr_details(repo_name, pr_num)
        
        print(f"🚀 [AUDIT STARTING] PR #{pr_num} on {repo_name}")

        # 3. Feed the Crew
        # These keys MUST match the {brackets} in your tasks.yaml
        inputs = {
            "diff": details["diff"],
            "pr_body": details["body"],
            "repo_name": repo_name,
            "tech_stack": "Auto-detected", # Scout will refine this
            "issue_description": "Review the PR body for specific goals and criteria."
        }

        # Kickoff the process
        crew_instance = PrToolCrew().crew()
        result = crew_instance.kickoff(inputs=inputs)

        print("\n✅ [AUDIT COMPLETE]")
        # 4. POST COMMENT TO GITHUB
        try:
            # result.pydantic contains the ReviewVerdict object 
            # defined in your schemas.py
            verdict = result.pydantic
            
            if verdict and verdict.comment_draft:
                print(f" Posting verdict to GitHub...")
                
                # We add a small header so everyone knows it's an AI audit
                final_comment = f"### 🤖 MergeMate AI Audit\n\n{verdict.comment_draft}"
                
                gh.post_pr_comment(repo_name, pr_num, final_comment)
            else:
                print("⚠️ No comment draft found in the AI's output.")
                
        except Exception as e:
            print(f"❌ Error extracting verdict: {str(e)}")
            # Fallback: if pydantic fails, try printing the raw result
            print(f"Raw Output: {result.raw}")

    return {"status": "accepted"}

@app.get("/")
async def root():
    return {"message": "MergeMate Auditor is Online"}