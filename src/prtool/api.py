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



def _detect_tech_stack(diff: str) -> str:
    """
    Detect tech stack from diff — reads file paths, imports, and config files.
    Covers frameworks (React, Django, Next.js, Spring, Rails) not just languages.
    No LLM call needed — pure string matching is fast and accurate enough.
    """
    import re

    # All changed file paths
    files = re.findall(r'\+\+\+ b/(.+)', diff)
    exts = {f.rsplit(".", 1)[-1].lower() for f in files if "." in f}
    filenames = {f.rsplit("/", 1)[-1].lower() for f in files}

    # All added lines (imports, config values)
    added_lines = " ".join(re.findall(r'^\+(.+)', diff, re.MULTILINE))

    # --- Framework detection (order matters — more specific first) ---

    # Next.js (TypeScript/JavaScript + Next-specific imports)
    if "next" in added_lines.lower() or any("next.config" in f for f in filenames):
        return "Next.js/TypeScript" if exts & {"ts", "tsx"} else "Next.js/JavaScript"

    # React (jsx/tsx files or React imports)
    if exts & {"jsx", "tsx"} or "from 'react'" in added_lines or 'from "react"' in added_lines:
        lang = "TypeScript" if exts & {"ts", "tsx"} else "JavaScript"
        return f"React/{lang}"

    # Vue
    if "vue" in exts or "from 'vue'" in added_lines:
        return "Vue.js"

    # Django (manage.py, django imports, models.py patterns)
    if any("django" in f for f in filenames) or "from django" in added_lines or "import django" in added_lines:
        return "Python/Django"

    # FastAPI / Flask
    if "from fastapi" in added_lines or "import fastapi" in added_lines:
        return "Python/FastAPI"
    if "from flask" in added_lines or "import flask" in added_lines:
        return "Python/Flask"

    # Spring Boot
    if "springframework" in added_lines.lower() or any("application.properties" in f for f in filenames):
        return "Java/Spring Boot"

    # Rails
    if "rb" in exts and ("rails" in added_lines.lower() or any("gemfile" in f for f in filenames)):
        return "Ruby/Rails"

    # Express / Node
    if "express" in added_lines.lower() and exts & {"js", "ts"}:
        return "Node.js/Express"

    # --- Language fallback (when no framework detected) ---
    if "py" in exts:
        return "Python"
    if exts & {"ts", "tsx"}:
        return "TypeScript"
    if exts & {"js", "jsx"}:
        return "JavaScript"
    if "go" in exts:
        return "Go"
    if "rs" in exts:
        return "Rust"
    if "java" in exts:
        return "Java"
    if "rb" in exts:
        return "Ruby"

    return "Unknown"



def _post_fallback_comment(gh, repo_name: str, pr_num: int, error: str, result=None):
    """
    Always posts something to the PR — never goes silent on failure.
    Tries to extract partial output from result.raw before giving up.
    """
    raw_snippet = ""
    if result is not None:
        try:
            raw = getattr(result, "raw", "") or ""
            if raw.strip():
                raw_snippet = f"\n\nPartial output:\n```\n{raw[:1000]}\n```"
        except Exception:
            pass

    comment = (
        f"### PR-Pilot AI Audit\n\n"
        f"Review encountered an issue and could not complete normally.\n\n"
        f"**Error:** `{error[:300]}`"
        f"{raw_snippet}\n\n"
        f"Push a new commit to trigger a fresh review."
    )
    try:
        gh.post_pr_comment(repo_name, pr_num, comment)
    except Exception as post_err:
        print(f"❌ Could not post fallback comment: {post_err}")


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
    pr_branch = data["pull_request"]["head"]["ref"]   # branch name for test runner
    install_id = data["installation"]["id"]

    # 5. Fetch live PR details — raises RuntimeError if diff is missing/empty
    gh = GitHubManager(install_id)
    try:
        details = gh.get_pr_details(repo_name, pr_num)
    except RuntimeError as e:
        print(f"❌ Could not fetch PR details: {e}")
        gh.post_pr_comment(
            repo_name, pr_num,
            f"### 🤖 MergeMate AI Audit\n\n"
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
        "tech_stack": _detect_tech_stack(details["diff"]),
        "issue_description": details["issue_body"],  # real issue, not a placeholder
        "pr_branch": pr_branch,              # for test executor sandbox clone
        "github_token": gh.token,            # short-lived installation token (Option A)
        "current_datetime": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M %Z"),
    }

    # 7. Run the crew in a thread — never block the async event loop
    result = None
    try:
        crew_instance = PrToolCrew().crew()
        result = await asyncio.to_thread(crew_instance.kickoff, inputs=inputs)
    except Exception as e:
        print(f"❌ Crew failed: {e}")
        # Don't go silent — post what we know, then return
        _post_fallback_comment(gh, repo_name, pr_num, str(e), result)
        return {"status": "error", "reason": str(e)}

    print("\n✅ [AUDIT COMPLETE]")

    # 8. Post the verdict comment back to GitHub
    try:
        verdict = result.pydantic
        if verdict and verdict.comment_draft:
            print("📝 Posting verdict to GitHub...")
            final_comment = f"### PR-Pilot AI Audit\n\n{verdict.comment_draft}"
            gh.post_pr_comment(repo_name, pr_num, final_comment)
        elif result.raw:
            print("⚠️  No structured verdict — posting raw output.")
            gh.post_pr_comment(
                repo_name, pr_num,
                f"### PR-Pilot AI Audit\n\n{result.raw}"
            )
        else:
            gh.post_pr_comment(repo_name, pr_num,
                "### PR-Pilot AI Audit\n\nReview completed but produced no output. "
                "Please push a new commit to retry.")
    except Exception as e:
        print(f"❌ Error posting comment: {e}")
        _post_fallback_comment(gh, repo_name, pr_num, str(e), result)

    return {"status": "accepted"}


@app.get("/")
async def root():
    return {"message": "MergeMate Auditor is Online"}