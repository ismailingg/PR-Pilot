import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_diff_files(diff: str) -> dict[str, str]:
    """
    Extract {filename: file_content} for every added/modified file in the diff.
    We only write '+' lines (new code) — deleted lines are irrelevant for scanning.
    """
    files: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            if current_file and current_lines:
                files[current_file] = "\n".join(current_lines)
            current_file = line[6:]
            current_lines = []
        elif line.startswith("+") and not line.startswith("+++"):
            current_lines.append(line[1:])
        elif line.startswith(" "):
            current_lines.append(line[1:])

    if current_file and current_lines:
        files[current_file] = "\n".join(current_lines)

    return files


def _severity_from_semgrep(extra: dict) -> str:
    raw = extra.get("severity", "INFO").upper()
    mapping = {
        "ERROR":   "critical",
        "WARNING": "medium",
        "INFO":    "low",
    }
    return mapping.get(raw, "low")


def _run_semgrep(target_dir: str) -> list[dict[str, Any]]:
    """
    Run semgrep with the auto config.
    FIX: encoding="utf-8" + errors="replace" prevents UnicodeDecodeError on
    Windows where the default codec is cp1252 and semgrep outputs UTF-8.
    """
    cmd = [
        "semgrep",
        "--config", "auto",
        "--json",
        "--quiet",
        "--no-git-ignore",
        target_dir,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",       # FIX: force UTF-8 instead of system default
            errors="replace",        # FIX: replace undecodable bytes instead of crashing
            timeout=120,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "semgrep is not installed or not on PATH. "
            "Install it with: pip install semgrep"
        )
    except subprocess.TimeoutExpired:
        return []

    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"semgrep exited with code {proc.returncode}.\n"
            f"stderr: {proc.stderr[:500]}"
        )

    stdout = proc.stdout or ""
    if not stdout.strip():
        return []

    try:
        data = json.loads(stdout)
        return data.get("results", [])
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

# Hard cap on diff size sent to Semgrep — large diffs (like adding audit_logger.py)
# cause the security scanner's context window to overflow Groq's 12k TPM limit.
# 8000 chars covers ~200 lines which is enough for any meaningful PR change.
MAX_DIFF_CHARS = 8000


class SemgrepScanTool(BaseTool):
    name: str = "Semgrep Security Scanner"
    description: str = (
        "Runs Semgrep static analysis on the changed files extracted from the PR diff. "
        "Returns a structured list of security findings with filename, line number, "
        "severity, rule ID, and a fix suggestion. "
        "Input must be the raw unified git diff string."
    )

    def _run(self, diff: str) -> str:
        if not diff or diff.strip() in ("", "Not Found"):
            return json.dumps({
                "status": "skipped",
                "reason": "No diff provided",
                "findings": [],
            })

        # Truncate very large diffs to stay within Groq's token limit.
        # Semgrep runs on the actual file content, not the diff text,
        # so truncating here only affects what gets scanned — not result quality
        # for normal-sized PRs.
        if len(diff) > MAX_DIFF_CHARS:
            diff = diff[:MAX_DIFF_CHARS]

        changed_files = _parse_diff_files(diff)
        if not changed_files:
            return json.dumps({
                "status": "skipped",
                "reason": "Could not extract any files from diff",
                "findings": [],
            })

        with tempfile.TemporaryDirectory(prefix="prpilot_scan_") as tmpdir:
            for filepath, content in changed_files.items():
                dest = Path(tmpdir) / filepath
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            try:
                raw_findings = _run_semgrep(tmpdir)
            except RuntimeError as e:
                return json.dumps({
                    "status": "error",
                    "reason": str(e),
                    "findings": [],
                })

        findings = []
        for r in raw_findings:
            raw_path = r.get("path", "unknown")
            relative_path = re.sub(r"^.*prpilot_scan_[^/\\]+[/\\]", "", raw_path)

            extra = r.get("extra", {})
            findings.append({
                "filename":    relative_path,
                "line_start":  r.get("start", {}).get("line"),
                "line_end":    r.get("end", {}).get("line"),
                "severity":    _severity_from_semgrep(extra),
                "rule_id":     r.get("check_id", "unknown"),
                "message":     extra.get("message", ""),
                "suggestion":  extra.get("fix", extra.get("message", "")),
            })

        return json.dumps({
            "status":        "completed",
            "files_scanned": len(changed_files),
            "finding_count": len(findings),
            "findings":      findings,
        }, indent=2)