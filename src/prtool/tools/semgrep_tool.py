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
        # New file header: +++ b/path/to/file.py
        if line.startswith("+++ b/"):
            if current_file and current_lines:
                files[current_file] = "\n".join(current_lines)
            current_file = line[6:]  # strip "+++ b/"
            current_lines = []
        elif line.startswith("+") and not line.startswith("+++"):
            # Strip the leading '+' — this is the actual new source line
            current_lines.append(line[1:])
        elif line.startswith(" "):
            # Context line (unchanged) — include for accurate line numbers
            current_lines.append(line[1:])

    # Flush last file
    if current_file and current_lines:
        files[current_file] = "\n".join(current_lines)

    return files


def _severity_from_semgrep(extra: dict) -> str:
    """Map Semgrep severity strings to our FindingSeverity enum values."""
    raw = extra.get("severity", "INFO").upper()
    mapping = {
        "ERROR":   "critical",
        "WARNING": "medium",
        "INFO":    "low",
    }
    return mapping.get(raw, "low")


def _run_semgrep(target_dir: str) -> list[dict[str, Any]]:
    """
    Run semgrep with the auto config (covers security, secrets, best-practices).
    Returns the list of raw finding dicts from semgrep's JSON output.
    Raises RuntimeError if semgrep is not installed or crashes unexpectedly.
    """
    cmd = [
        "semgrep",
        "--config", "auto",
        "--json",
        "--quiet",           # suppress progress noise
        "--no-git-ignore",   # temp dir has no .gitignore
        target_dir,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,   # 2-minute hard cap per scan
        )
    except FileNotFoundError:
        raise RuntimeError(
            "semgrep is not installed or not on PATH. "
            "Install it with: pip install semgrep"
        )
    except subprocess.TimeoutExpired:
        return []   # timeout → return empty rather than crash the crew

    # semgrep exits 0 (no findings) or 1 (findings found) — both are fine.
    # Any other exit code is a real error.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"semgrep exited with code {proc.returncode}.\n"
            f"stderr: {proc.stderr[:500]}"
        )

    if not proc.stdout.strip():
        return []

    try:
        data = json.loads(proc.stdout)
        return data.get("results", [])
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

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

        # 1. Parse changed files out of the diff
        changed_files = _parse_diff_files(diff)
        if not changed_files:
            return json.dumps({
                "status": "skipped",
                "reason": "Could not extract any files from diff",
                "findings": [],
            })

        # 2. Write files to a temp directory
        with tempfile.TemporaryDirectory(prefix="prpilot_scan_") as tmpdir:
            for filepath, content in changed_files.items():
                # Recreate the directory structure inside tmpdir
                dest = Path(tmpdir) / filepath
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            # 3. Run semgrep
            try:
                raw_findings = _run_semgrep(tmpdir)
            except RuntimeError as e:
                return json.dumps({
                    "status": "error",
                    "reason": str(e),
                    "findings": [],
                })

        # 4. Normalise findings into our schema
        findings = []
        for r in raw_findings:
            # Strip the tmpdir prefix from the path so it looks like the real filepath
            raw_path = r.get("path", "unknown")
            # e.g. /tmp/prpilot_scan_abc123/auth.py  →  auth.py
            relative_path = re.sub(r"^.*prpilot_scan_[^/]+/", "", raw_path)

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
            "status":   "completed",
            "files_scanned": len(changed_files),
            "finding_count": len(findings),
            "findings": findings,
        }, indent=2)