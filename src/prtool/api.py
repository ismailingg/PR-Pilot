import hmac
import hashlib
import json
import os
import asyncio
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

from prtool.utils.github_manager import GitHubManager
from prtool.crew import PrToolCrew

load_dotenv()
app = FastAPI()


@app.post("/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    # 1. Read body once — parse manually to avoid double-read bug
    payload = await request.body()

    # 2. Guard: secret must exist before we try to use it
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="GITHUB_WEBHOOK_SECRET not configured")

    # 3. Signature verification
    expected_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(expected_sig, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 4. Parse body once from the bytes we already have
    data = json.loads(payload)
    action = data.get("action")

    # Trigger only on PR open or new commits pushed
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    repo_name = data["repository"]["full_name"]
    pr_num = data["pull_request"]["number"]
    install_id = data["installation"]["id"]

    # 5. Fetch live PR details — raises RuntimeError if diff is missing/empty
    gh = GitHubManager(install_id)
    try:
        details = gh.get_pr_details(repo_name, pr_num)
    except RuntimeError as e:
        print(f"❌ Could not fetch PR details: {e}")
        gh.post_pr_comment(
            repo_name, pr_num,
            f"###  PrPilot AI Audit\n\n"
            f"⚠️ Could not start review: `{e}`\n\n"
            f"Please ensure the PR contains code changes and try again."
        )
        return {"status": "error", "reason": str(e)}

    print(f"🚀 [AUDIT STARTING] PR #{pr_num} on {repo_name}")

    # 6. Build inputs — all keys must match {brackets} in tasks.yaml
    inputs = {
        "diff": details["diff"],
        "pr_body": details["body"],
        "repo_name": repo_name,
        "tech_stack": "Auto-detected",       # Scout agent will refine this
        "issue_description": details["issue_body"],  # real issue, not a placeholder
    }

    # 7. Run the crew in a thread — never block the async event loop
    try:
        crew_instance = PrToolCrew().crew()
        result = await asyncio.to_thread(crew_instance.kickoff, inputs=inputs)
    except Exception as e:
        print(f"❌ Crew failed: {e}")
        gh.post_pr_comment(
            repo_name, pr_num,
            f"### 🤖 PrPilot AI Audit\n\n"
            f"💥 Review failed with an internal error. Please re-open or push a new commit to retry."
        )
        return {"status": "error", "reason": str(e)}

    print("\n✅ [AUDIT COMPLETE]")

    # 8. Post the verdict comment back to GitHub
    try:
        verdict = result.pydantic
        if verdict and verdict.comment_draft:
            print("📝 Posting verdict to GitHub...")
            final_comment = f"### 🤖 MergeMate AI Audit\n\n{verdict.comment_draft}"
            gh.post_pr_comment(repo_name, pr_num, final_comment)
        else:
            print("⚠️  No comment_draft in verdict — posting raw output.")
            gh.post_pr_comment(
                repo_name, pr_num,
                f"### 🤖 MergeMate AI Audit\n\n```\n{result.raw}\n```"
            )
    except Exception as e:
        print(f"❌ Error posting comment: {e}")
        print(f"Raw output: {result.raw}")

    return {"status": "accepted"}


@app.get("/")
async def root():
    return {"message": "PrPilot Auditor is Online"}