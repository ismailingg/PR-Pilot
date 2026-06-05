"""
merge_sim_tool.py

Simulates merging a PR branch into main on the host machine (no Docker needed —
git operations carry no untrusted code execution risk).

Steps:
1. Shallow-clone the repo with enough history for a merge attempt
2. Attempt git merge --no-commit --no-ff <pr_branch>
3. Collect conflicting files if any
4. Always abort to leave no trace
5. Return structured result
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Any

from crewai.tools import BaseTool


# ---------------------------------------------------------------------------
# Core git operations
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a git command, return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"git {args[0]} timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "", "git is not installed or not on PATH"


def _inject_token(repo_url: str, token: str) -> str:
    """Inject GitHub token into HTTPS clone URL."""
    if token and "github.com" in repo_url:
        return repo_url.replace("https://", f"https://x-access-token:{token}@")
    return repo_url


# ---------------------------------------------------------------------------
# Merge simulation
# ---------------------------------------------------------------------------

def simulate_merge(
    repo_url: str,
    pr_branch: str,
    base_branch: str,
    token: str,
) -> dict[str, Any]:
    """
    Clone the repo, simulate merging pr_branch into base_branch,
    collect any conflicts, then abort cleanly.
    """
    clone_url = _inject_token(repo_url, token)
    tmpdir = tempfile.mkdtemp(prefix="prpilot_mergesim_")

    try:
        start = time.time()

        # 1. Shallow clone — depth 50 gives enough history for most merges
        rc, _, err = _run_git(
            ["clone", "--depth=50", "--no-single-branch", clone_url, tmpdir],
            cwd="/tmp",
            timeout=120,
        )
        if rc != 0:
            return {
                "status": "error",
                "reason": f"Clone failed: {err[:300]}",
                "conflicts": [],
                "conflicting_files": [],
                "mergeable": None,
            }

        # 2. Make sure base branch exists locally
        rc, _, err = _run_git(["checkout", base_branch], cwd=tmpdir)
        if rc != 0:
            # Try origin/base_branch
            rc, _, err = _run_git(
                ["checkout", "-b", base_branch, f"origin/{base_branch}"],
                cwd=tmpdir,
            )
            if rc != 0:
                return {
                    "status": "error",
                    "reason": f"Could not checkout base branch '{base_branch}': {err[:200]}",
                    "conflicts": [],
                    "conflicting_files": [],
                    "mergeable": None,
                }

        # 3. Fetch the PR branch
        rc, _, err = _run_git(
            ["fetch", "origin", f"{pr_branch}:{pr_branch}"],
            cwd=tmpdir,
            timeout=60,
        )
        if rc != 0:
            return {
                "status": "error",
                "reason": f"Could not fetch PR branch '{pr_branch}': {err[:200]}",
                "conflicts": [],
                "conflicting_files": [],
                "mergeable": None,
            }

        # 4. Attempt merge — no-commit so nothing is written permanently
        rc, stdout, stderr = _run_git(
            ["merge", "--no-commit", "--no-ff", pr_branch],
            cwd=tmpdir,
        )

        mergeable = (rc == 0)
        conflicting_files = []

        if not mergeable:
            # 5. Collect conflicting files
            _, conflict_out, _ = _run_git(
                ["diff", "--name-only", "--diff-filter=U"],
                cwd=tmpdir,
            )
            conflicting_files = [
                f.strip() for f in conflict_out.splitlines() if f.strip()
            ]

        # 6. Always abort — leave the repo clean
        _run_git(["merge", "--abort"], cwd=tmpdir)

        duration = round(time.time() - start, 1)

        if mergeable:
            return {
                "status": "completed",
                "mergeable": True,
                "conflicts": 0,
                "conflicting_files": [],
                "base_branch": base_branch,
                "pr_branch": pr_branch,
                "duration_seconds": duration,
                "summary": f"Clean merge into {base_branch} — no conflicts.",
            }
        else:
            return {
                "status": "completed",
                "mergeable": False,
                "conflicts": len(conflicting_files),
                "conflicting_files": conflicting_files,
                "base_branch": base_branch,
                "pr_branch": pr_branch,
                "duration_seconds": duration,
                "summary": (
                    f"{len(conflicting_files)} conflict(s) detected when merging "
                    f"into {base_branch}: {', '.join(conflicting_files)}"
                ),
            }

    except Exception as e:
        return {
            "status": "error",
            "reason": str(e),
            "conflicts": [],
            "conflicting_files": [],
            "mergeable": None,
        }
    finally:
        # Always clean up — temp dir gone regardless of outcome
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CrewAI Tool
# ---------------------------------------------------------------------------

class MergeSimTool(BaseTool):
    name: str = "Merge Simulation Tool"
    description: str = (
        "Simulates merging a PR branch into the base branch (usually main) "
        "by cloning the repository and attempting a git merge --no-commit. "
        "Returns whether the merge would be clean or conflicted, and lists "
        "any conflicting files. Never actually merges — always aborts cleanly."
    )

    def _run(
        self,
        repo_url: str,
        pr_branch: str,
        github_token: str = "",
        base_branch: str = "main",
    ) -> str:
        if not repo_url or not pr_branch:
            return json.dumps({
                "status": "error",
                "reason": "repo_url and pr_branch are required.",
                "mergeable": None,
                "conflicting_files": [],
            })

        result = simulate_merge(repo_url, pr_branch, base_branch, github_token)
        return json.dumps(result, indent=2)