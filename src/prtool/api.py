import hmac
import hashlib
import json
import os
import asyncio
import time
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

from prtool.utils.github_manager import GitHubManager
from prtool.crew import PrToolCrew
from prtool.dashboard import dashboard_router
from prtool.audit_logger import (
    init_db,
    log_run_started,
    log_run_completed,
    log_run_failed,
    log_agent_step,
)

load_dotenv()


BANNER = (
    "\033[36m\n"
    r"  ____  ____     ____  _ __      __ " + "\n"
    r" / __ \/ __ \   / __ \(_) /___  / /_" + "\n"
    r"/ /_/ / /_/ /  / /_/ / / / __ \/ __/" + "\n"
    r"/ ____/ _, _/  / ____/ / / /_/ / /_  " + "\n"
    r"/_/   /_/ |_|  /_/   /_/_/\____/\__/  " + "\n"
    "\033[0m\033[1m\n"
    "PR Pilot\033[0m\n"
    "\033[90m=====================================================\033[0m\n"
    "\033[32m  >> Your Virtual Senior Engineer Is On Duty\033[0m\n"
    "\033[90m=====================================================\033[0m\n"
)


print(BANNER)
app = FastAPI()

# Mount dashboard
app.include_router(dashboard_router)

# Initialise SQLite tables once at startup
init_db()

# ---------------------------------------------------------------------------
# Concurrency control — limits simultaneous crew executions per tier
# Free tier:  1 at a time — two concurrent reviews would exceed Groq's 12k TPM
# Paid tier:  3 at a time — paid APIs have much higher rate limits
# Local tier: 1 at a time — CPU inference can't handle parallel workloads
# ---------------------------------------------------------------------------
_LLM_TIER = os.getenv("LLM_TIER", "free").lower()
_MAX_CONCURRENT = 3 if _LLM_TIER == "paid" else 1
_review_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

# ---------------------------------------------------------------------------
# Diff size limits per tier
# Free tier: Groq has 12k TPM limit — truncate large diffs
# Paid/Local: no limit — pass full diff always
# ---------------------------------------------------------------------------
_FREE_DIFF_CHAR_LIMIT = 12000   # ~300 lines — safe for Groq 12k TPM


def _truncate_diff_for_tier(diff: str, tier: str) -> tuple[str, bool]:
    """
    Returns (diff_to_use, was_truncated).
    Free tier truncates to _FREE_DIFF_CHAR_LIMIT chars.
    Paid and local tiers always get the full diff.
    """
    if tier == "free" and len(diff) > _FREE_DIFF_CHAR_LIMIT:
        truncated = diff[:_FREE_DIFF_CHAR_LIMIT]
        # Trim to last complete line so we don't cut mid-line
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        print(f"  Free tier: diff truncated from {len(diff)} to {len(truncated)} chars")
        return truncated, True
    return diff, False


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
        print(f" Could not post fallback comment: {post_err}")


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

    repo_name  = data["repository"]["full_name"]
    pr_num     = data["pull_request"]["number"]
    pr_branch  = data["pull_request"]["head"]["ref"]
    install_id = data["installation"]["id"]

    # 5. Fetch live PR details — raises RuntimeError if diff is missing/empty
    gh = GitHubManager(install_id)
    try:
        details = gh.get_pr_details(repo_name, pr_num)
    except RuntimeError as e:
        print(f" Could not fetch PR details: {e}")
        gh.post_pr_comment(
            repo_name, pr_num,
            f"### PR-Pilot AI Audit\n\n"
            f"Could not start review: `{e}`\n\n"
            f"Please ensure the PR contains code changes and try again."
        )
        return {"status": "error", "reason": str(e)}

    tech_stack = _detect_tech_stack(details["diff"])
    pr_author  = details.get("pr_author", "unknown")
    run_id     = str(uuid.uuid4())
    start_time = time.time()

    print(f" [AUDIT STARTING] PR #{pr_num} on {repo_name} | run_id={run_id}")

    # 6. Log run start to SQLite
    log_run_started(
        run_id=run_id,
        repo_name=repo_name,
        pr_number=pr_num,
        pr_branch=pr_branch,
        pr_author=pr_author,
        tech_stack=tech_stack,
    )

    # 7. Apply tier-based diff truncation
    # Free tier: truncate to stay within Groq's 12k TPM limit
    # Paid/local tier: always pass the full diff for complete analysis
    llm_tier = os.getenv("LLM_TIER", "free").lower()
    diff_to_use, was_truncated = _truncate_diff_for_tier(details["diff"], llm_tier)

    diff_lines = len([l for l in diff_to_use.splitlines() if l.startswith("+")])
    pr_scope   = "large" if diff_lines > 200 else "medium" if diff_lines > 50 else "small"

    # 8. Build inputs — all keys must match {brackets} in tasks.yaml
    inputs = {
        "diff":              diff_to_use,
        "pr_body":           details["body"],
        "repo_name":         repo_name,
        "tech_stack":        tech_stack,
        "issue_description": details["issue_body"],
        "pr_branch":         pr_branch,
        "github_token":      gh.token,
        "current_datetime":  datetime.now().strftime("%Y-%m-%d %H:%M %Z"),
        "pr_scope":          pr_scope,
        "diff_line_count":   diff_lines,
        "diff_truncated":    was_truncated,   # lets decider note truncation in comment
    }

    # 9. Run the crew in a thread — never block the async event loop
    # Semaphore limits concurrent reviews based on tier to avoid rate limit errors
    result = None
    try:
        async with _review_semaphore:
            print(f" Semaphore acquired (max {_MAX_CONCURRENT} concurrent) — starting crew")
            crew_instance = PrToolCrew().crew()
            result = await asyncio.to_thread(crew_instance.kickoff, inputs=inputs)
    except Exception as e:
        duration = round(time.time() - start_time, 1)
        print(f" Crew failed: {e}")
        log_run_failed(run_id, str(e), duration)
        _post_fallback_comment(gh, repo_name, pr_num, str(e), result)
        return {"status": "error", "reason": str(e)}

    duration = round(time.time() - start_time, 1)
    print(f"\n [AUDIT COMPLETE] duration={duration}s")

    # 10. Post the verdict comment back to GitHub
    comment_posted = False
    verdict_str    = "unknown"
    confidence     = 0.0
    quality_score  = 0.0
    security_score = 0.0

    try:
        verdict = result.pydantic
        if verdict and verdict.comment_draft:
            print(" Posting verdict to GitHub...")
            final_comment = f"### PR-Pilot AI Audit\n\n{verdict.comment_draft}"
            gh.post_pr_comment(repo_name, pr_num, final_comment)
            comment_posted = True
            verdict_str = (
                verdict.verdict.value
                if hasattr(verdict.verdict, "value")
                else str(verdict.verdict)
            )
            confidence = float(verdict.confidence)
        elif result.raw:
            print("  No structured verdict — posting raw output.")
            gh.post_pr_comment(
                repo_name, pr_num,
                f"### PR-Pilot AI Audit\n\n{result.raw}"
            )
            comment_posted = True
        else:
            gh.post_pr_comment(
                repo_name, pr_num,
                "### PR-Pilot AI Audit\n\nReview completed but produced no output. "
                "Please push a new commit to retry."
            )

        # Extract quality/security scores and log each agent step
        try:
            for task_out in (result.tasks_output or []):
                # Pull scores from the verification task pydantic output
                if hasattr(task_out, "pydantic") and task_out.pydantic:
                    p = task_out.pydantic
                    if hasattr(p, "quality_score"):
                        quality_score  = float(p.quality_score)
                    if hasattr(p, "security_score"):
                        security_score = float(p.security_score)

                # Log the agent step
                log_agent_step(
                    run_id=run_id,
                    agent_name=str(getattr(task_out, "agent", "unknown")),
                    task_name=str(getattr(task_out, "name", "unknown")),
                    output=getattr(task_out, "raw", "") or "",
                )
        except Exception as log_err:
            print(f"  Could not log agent steps: {log_err}")

    except Exception as e:
        print(f" Error posting comment: {e}")
        _post_fallback_comment(gh, repo_name, pr_num, str(e), result)

    # 11. Log run completion
    log_run_completed(
        run_id=run_id,
        verdict=verdict_str,
        confidence=confidence,
        quality_score=quality_score,
        security_score=security_score,
        comment_posted=comment_posted,
        duration_seconds=duration,
    )

    return {"status": "accepted", "run_id": run_id}


@app.get("/")
async def root():
    return {"message": "PR-Pilot Auditor is Online"}