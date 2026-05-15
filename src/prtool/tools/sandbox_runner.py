"""
sandbox_runner.py

Clones a PR branch, detects the project type (including multi-folder
frameworks like MERN, Django+React, etc.), runs the test suite inside
an isolated Docker sandbox, and returns structured results.

Key fixes over v1:
- Recursive marker search: finds backend/, frontend/, server/ subdirs
- Network NOT disabled during run: clone + install both need internet;
  isolation comes from --memory, --cpus, --user sandbox, and --rm
- Correct work_dir injected into Docker script so cd lands in the right place
- Multiple project detection: MERN runs Node AND Python if both found
"""

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SANDBOX_IMAGE    = "prpilot-sandbox"
TIMEOUT_SECONDS  = 180          # 3-minute hard kill per container
MEMORY_LIMIT     = "512m"
CPU_LIMIT        = "1.0"
MAX_LOG_LINES    = 60           # truncate long test output sent to LLM

# Subdirectory names we scan inside the repo root
# (keeps detection fast — we don't recurse infinitely)
COMMON_SUBDIRS = [
    "backend", "frontend", "server", "client", "api",
    "app", "src", "web", "service", "apps",
]

# ---------------------------------------------------------------------------
# Language profiles
# ---------------------------------------------------------------------------

LANGUAGE_PROFILES = [
    {
        "name": "python",
        "markers": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "manage.py", "pytest.ini", "tox.ini", ".pytest.ini"],
        # Install priority: requirements.txt → editable install → bare install → skip
        "install": (
            "pip install -q -r requirements.txt 2>/dev/null || "
            "pip install -q -e '.[dev,test]' 2>/dev/null || "
            "pip install -q -e . 2>/dev/null || true"
        ),
        # Test priority chain:
        # 1. make test      — repo defines its own command (most flexible)
        # 2. tox            — if tox.ini exists
        # 3. pytest with --import-mode=importlib — works for any folder structure,
        #    no __init__.py or package install needed
        # 4. unittest discover — built-in fallback, no pytest needed
        "test": (
            "(make test 2>/dev/null) || "
            "(tox 2>/dev/null) || "
            "(python3 -m pytest --import-mode=importlib --tb=short -q 2>&1) || "
            "(python3 -m unittest discover -s tests -q 2>&1)"
        ),
    },
    {
        "name": "nodejs",
        "markers": ["package.json"],
        # Install priority: npm ci (clean) → npm install (relaxed) → yarn → pnpm
        "install": (
            "npm ci --silent 2>&1 || "
            "npm install --silent 2>&1 || "
            "yarn install --silent 2>&1 || "
            "pnpm install --silent 2>&1 || true"
        ),
        # Test priority: npm → yarn → pnpm
        # --passWithNoTests prevents exit code 1 when no tests exist yet
        "test": (
            "(npm test -- --passWithNoTests 2>&1) || "
            "(yarn test --passWithNoTests 2>&1) || "
            "(pnpm test 2>&1)"
        ),
    },
    {
        "name": "go",
        "markers": ["go.mod"],
        "install": "go mod download 2>&1",
        "test": "go test ./... 2>&1",
    },
    {
        "name": "rust",
        "markers": ["Cargo.toml"],
        "install": "/home/sandbox/.cargo/bin/cargo fetch 2>&1",
        "test": "/home/sandbox/.cargo/bin/cargo test 2>&1",
    },
    {
        "name": "java_maven",
        "markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "install": (
            "mvn -q dependency:resolve 2>/dev/null || "
            "./gradlew dependencies --quiet 2>/dev/null || true"
        ),
        # Maven first, Gradle fallback
        "test": (
            "(mvn -q test 2>&1) || "
            "(./gradlew test 2>&1)"
        ),
    },
    {
        "name": "ruby",
        "markers": ["Gemfile", "Rakefile"],
        "install": "bundle install --quiet 2>&1 || true",
        # rake → rspec → minitest
        "test": (
            "(bundle exec rake test 2>&1) || "
            "(bundle exec rspec 2>&1) || "
            "(bundle exec ruby -Itest test/**/*_test.rb 2>&1)"
        ),
    },
]

# Map marker filename → profile name for O(1) lookup
_MARKER_TO_PROFILE: dict[str, dict] = {}
for _p in LANGUAGE_PROFILES:
    for _m in _p["markers"]:
        _MARKER_TO_PROFILE[_m] = _p


# ---------------------------------------------------------------------------
# Language detection — recursive, returns list for monorepos
# ---------------------------------------------------------------------------

def _find_projects(repo_dir: str) -> list[dict]:
    """
    Scan repo root + COMMON_SUBDIRS for recognised project markers.
    Returns a list of dicts: {profile, work_dir, relative_work_dir}
    so the runner knows which directory to cd into inside the container.

    For a plain project:  [{"profile": python_profile, "work_dir": "/tmp/.../repo"}]
    For MERN:             [{"profile": nodejs_profile,  "work_dir": ".../repo/frontend"},
                           {"profile": python_profile,  "work_dir": ".../repo/backend"}]
    """
    found: list[dict] = []
    seen_profiles: set[str] = set()   # avoid running Python twice if two subdirs match

    search_dirs: list[tuple[str, str]] = [
        (repo_dir, ".")   # (absolute_path, relative_path_from_repo_root)
    ]
    for subdir_name in COMMON_SUBDIRS:
        candidate = Path(repo_dir) / subdir_name
        if candidate.is_dir():
            search_dirs.append((str(candidate), subdir_name))

    for abs_dir, rel_dir in search_dirs:
        for marker_file, profile in _MARKER_TO_PROFILE.items():
            if (Path(abs_dir) / marker_file).exists():
                if profile["name"] not in seen_profiles:
                    seen_profiles.add(profile["name"])
                    found.append({
                        "profile": profile,
                        "abs_work_dir": abs_dir,
                        "rel_work_dir": rel_dir,   # relative to repo root
                    })
                break   # one match per directory is enough

    # Fallback: if no markers found but a tests/ dir with .py files exists,
    # treat as a bare Python project (no requirements.txt yet)
    if not found:
        python_profile = next(p for p in LANGUAGE_PROFILES if p["name"] == "python")
        tests_dir = Path(repo_dir) / "tests"
        has_py_tests = (
            tests_dir.is_dir() and
            any(tests_dir.glob("test_*.py"))
        )
        # Also check for any .py files in root that look like test files
        root_py_tests = any(Path(repo_dir).glob("test_*.py"))
        if has_py_tests or root_py_tests:
            found.append({
                "profile": python_profile,
                "abs_work_dir": repo_dir,
                "rel_work_dir": ".",
            })

    return found


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _image_exists() -> bool:
    r = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True, timeout=10,
    )
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Run one project inside Docker
# ---------------------------------------------------------------------------

def _run_project_in_sandbox(
    repo_url: str,
    branch: str,
    profile: dict,
    rel_work_dir: str,
) -> dict[str, Any]:
    """
    Clone the branch, cd into rel_work_dir, install deps, run tests.
    Network is kept ON throughout (clone + install both need it).
    Isolation is enforced via --memory, --cpus, --user sandbox, and --rm.
    """
    # cd path inside container — "." means repo root
    cd_into = f"cd repo/{rel_work_dir}" if rel_work_dir != "." else "cd repo"

    script = f"""
cd /home/sandbox

echo "==> Cloning branch: {branch}"
git clone --depth=1 --branch {branch} {repo_url} repo 2>&1
if [ $? -ne 0 ]; then echo "CLONE_FAILED"; exit 1; fi

echo "==> Entering project directory"
{cd_into}

echo "==> Installing dependencies"
{profile['install']}

echo "==> Running tests"
{profile['test']}
exit $?
"""

    cmd = [
        "docker", "run",
        "--rm",                          # delete container after exit
        f"--memory={MEMORY_LIMIT}",      # hard RAM cap
        f"--cpus={CPU_LIMIT}",           # CPU limit
        "--user", "sandbox",             # non-root — can't write to host
        # NOTE: --network=none removed intentionally.
        # Clone + package install both need network.
        # Full network isolation is a Phase 4 hardening task.
        SANDBOX_IMAGE,
        "/bin/bash", "-c", script,
    ]

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        duration = round(time.time() - start, 1)
        combined = ((proc.stdout or "") + (proc.stderr or "")).strip()

        # Keep last MAX_LOG_LINES so LLM context doesn't explode
        lines = combined.splitlines()
        if len(lines) > MAX_LOG_LINES:
            lines = [f"... ({len(lines) - MAX_LOG_LINES} lines truncated) ..."] + lines[-MAX_LOG_LINES:]

        return {
            "exit_code":       proc.returncode,
            "passed":          proc.returncode == 0,
            "duration_seconds": duration,
            "logs":            "\n".join(lines),
            "timed_out":       False,
        }

    except subprocess.TimeoutExpired:
        return {
            "exit_code":        -1,
            "passed":           False,
            "duration_seconds": TIMEOUT_SECONDS,
            "logs":             f"⚠️ Container killed after {TIMEOUT_SECONDS}s timeout.",
            "timed_out":        True,
        }


# ---------------------------------------------------------------------------
# Parse test counts from runner output
# ---------------------------------------------------------------------------

def _parse_test_counts(logs: str, language: str) -> dict[str, int]:
    counts = {"total": 0, "passed": 0, "failed": 0}

    if language == "python":
        m = re.search(r"(\d+) passed", logs)
        if m: counts["passed"] = int(m.group(1))
        m = re.search(r"(\d+) failed", logs)
        if m: counts["failed"] = int(m.group(1))
        counts["total"] = counts["passed"] + counts["failed"]

    elif language == "nodejs":
        # Jest: "Tests: 2 failed, 5 passed, 7 total"
        m = re.search(r"(\d+) passed", logs)
        if m: counts["passed"] = int(m.group(1))
        m = re.search(r"(\d+) failed", logs)
        if m: counts["failed"] = int(m.group(1))
        # Mocha: "5 passing" / "2 failing"
        if counts["passed"] == 0:
            m = re.search(r"(\d+) passing", logs)
            if m: counts["passed"] = int(m.group(1))
        if counts["failed"] == 0:
            m = re.search(r"(\d+) failing", logs)
            if m: counts["failed"] = int(m.group(1))
        counts["total"] = counts["passed"] + counts["failed"]

    elif language == "go":
        counts["passed"] = logs.count("\nok ")
        counts["failed"] = logs.count("FAIL\t")
        counts["total"]  = counts["passed"] + counts["failed"]

    elif language == "rust":
        m = re.search(r"(\d+) passed", logs)
        if m: counts["passed"] = int(m.group(1))
        m = re.search(r"(\d+) failed", logs)
        if m: counts["failed"] = int(m.group(1))
        counts["total"] = counts["passed"] + counts["failed"]

    elif language == "java_maven":
        # Maven: "Tests run: 7, Failures: 0, Errors: 0"
        m = re.search(r"Tests run:\s*(\d+)", logs)
        if m: counts["total"] = int(m.group(1))
        m = re.search(r"Failures:\s*(\d+)", logs)
        if m: counts["failed"] = int(m.group(1))
        counts["passed"] = counts["total"] - counts["failed"]

    elif language == "ruby":
        # RSpec: "5 examples, 0 failures"
        m = re.search(r"(\d+) examples?", logs)
        if m: counts["total"] = int(m.group(1))
        m = re.search(r"(\d+) failures?", logs)
        if m: counts["failed"] = int(m.group(1))
        counts["passed"] = counts["total"] - counts["failed"]

    return counts


# ---------------------------------------------------------------------------
# CrewAI Tool
# ---------------------------------------------------------------------------

class SandboxTestRunnerTool(BaseTool):
    name: str = "Sandbox Test Runner"
    description: str = (
        "Clones a GitHub PR branch into an isolated Docker sandbox, "
        "detects the project type including multi-folder frameworks "
        "(MERN, Django+React, etc.), installs dependencies, runs the "
        "test suite, and returns structured pass/fail results with logs."
    )

    def _run(self, repo_url: str, branch: str, github_token: str = "") -> str:
        repo_url_base = repo_url
        token         = github_token

        # --- 2. Inject token into clone URL (Option A — short-lived install token) ---
        if token and "github.com" in repo_url_base:
            repo_url = repo_url_base.replace("https://", f"https://x-access-token:{token}@")
        else:
            repo_url = repo_url_base

        # --- 3. Preflight: Docker available? Image built? ---
        if not _docker_available():
            return json.dumps({
                "status": "skipped",
                "reason": "Docker is not running or not installed on this server.",
                "passed": False,
            })

        if not _image_exists():
            return json.dumps({
                "status": "skipped",
                "reason": (
                    f"Docker image '{SANDBOX_IMAGE}' not found. "
                    f"Build it first: docker build -t {SANDBOX_IMAGE} ."
                ),
                "passed": False,
            })

        # --- 4. Shallow clone to a temp dir for language detection ---
        with tempfile.TemporaryDirectory(prefix="prpilot_detect_") as tmpdir:
            clone = subprocess.run(
                ["git", "clone", "--depth=1", "--branch", branch, repo_url, f"{tmpdir}/repo"],
                capture_output=True, text=True, timeout=60,
            )
            if clone.returncode != 0:
                return json.dumps({
                    "status": "error",
                    "reason": f"Clone failed: {clone.stderr[:300]}",
                    "passed": False,
                })

            projects = _find_projects(f"{tmpdir}/repo")

        # --- 5. Nothing recognised ---
        if not projects:
            return json.dumps({
                "status": "skipped",
                "reason": (
                    "No recognised project files found in root or common subdirectories "
                    "(backend/, frontend/, server/, client/, api/, app/). "
                    "Checked for: requirements.txt, pyproject.toml, manage.py, "
                    "package.json, go.mod, Cargo.toml, pom.xml, Gemfile."
                ),
                "passed": False,
                "language": "unknown",
            })

        # --- 6. Run each detected project in its own container ---
        all_results = []
        overall_passed = True

        for project in projects:
            profile     = project["profile"]
            rel_work_dir = project["rel_work_dir"]

            print(f"🐳 Running {profile['name']} tests in {rel_work_dir}...")
            result = _run_project_in_sandbox(repo_url, branch, profile, rel_work_dir)
            counts = _parse_test_counts(result["logs"], profile["name"])

            if not result["passed"]:
                overall_passed = False

            all_results.append({
                "language":         profile["name"],
                "work_dir":         rel_work_dir,
                "passed":           result["passed"],
                "exit_code":        result["exit_code"],
                "duration_seconds": result["duration_seconds"],
                "timed_out":        result["timed_out"],
                "test_counts":      counts,
                "logs":             result["logs"],
            })

        # --- 7. Build summary ---
        languages_run = [r["language"] for r in all_results]
        any_timeout   = any(r["timed_out"] for r in all_results)

        return json.dumps({
            "status":           "timeout" if any_timeout else "completed",
            "projects_found":   len(all_results),
            "languages":        languages_run,
            "overall_passed":   overall_passed,
            "results":          all_results,
        }, indent=2)