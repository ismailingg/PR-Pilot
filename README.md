```
  ____  ____     ____  _ __      __ 
 / __ \/ __ \   / __ \(_) /___  / /_
/ /_/ / /_/ /  / /_/ / / / __ \/ __/
/ ____/ _, _/  / ____/ / / /_/ / /_  
/_/   /_/ |_|  /_/   /_/_/\____/\__/  

PR Pilot
=====================================================
  >> Your Virtual Senior Engineer Is On Duty
=====================================================
```

# PR-Pilot

PR-Pilot is a self-hosted AI code review agent that integrates with GitHub and automatically reviews pull requests — flagging real bugs with line citations, running Semgrep security scans, detecting merge conflicts before they happen, and posting structured feedback with a confidence score directly to your PR. Runs entirely on your infrastructure. On the local tier, no code ever leaves your machine.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Powered by CrewAI](https://img.shields.io/badge/powered%20by-CrewAI-purple)

---

## Sample Review Comment

```
### PR-Pilot AI Review

**Verdict**: Strongly Recommended to Merge
**Confidence**: 93%

#### Summary
The PR adds unregister_api_key() which removes a service's API key registration
from the module-level dict. The implementation is focused and achieves the stated
goal with no side effects on existing functionality.

#### Key Findings

**Positive Points**
- unregister_api_key(): checks service_name exists in api_keys via `in` guard
  before deletion — prevents KeyError on unknown services, returns False correctly
- Consistent with existing register_api_key() pattern in the same module

**Suggestions for Improvement**
None — implementation is clean and focused.

#### Security & Risk Assessment
- Security scan: Clean (no issues found)
- Merge simulation: Clean — no conflicts with main
- Potential side effects: None detected

#### Recommendation
**Ready to merge.**

---
**PR-Pilot Analysis Details** *(expand for details)*
- Intent match: 100% (all criteria met)
- Code quality score: 9.0/10
- Security score: 9.0/10
- Generated at: 2026-06-12 10:36
```

---

## What It Does

When a PR is opened or updated on a connected repository, PR-Pilot:

1. Fetches the diff and linked issue from GitHub
2. Extracts the intent and acceptance criteria from the PR description
3. Reviews the code diff mechanically — not just the description, citing actual lines
4. Runs Semgrep static analysis for real security vulnerabilities
5. Simulates a git merge to detect conflicts before they reach main
6. Posts a structured review comment with verdict, confidence score, and findings
7. Logs every review to a local SQLite database viewable on a built-in dashboard

---

## Agent Pipeline

```
PR opened / updated
        ↓
Intent Extractor    — reads PR description and linked issue, extracts acceptance criteria
        ↓
Diff Reviewer       — reviews changed code mechanically, line by line, never paraphrases
        ↓
Security Scanner    — runs Semgrep SAST, maps findings to OWASP categories
        ↓
Merge Sim Engineer  — simulates git merge --no-commit, detects file conflicts
        ↓
Verifier            — cross-references findings against intent, filters false positives
        ↓
Decider             — writes the final GitHub comment with verdict and confidence score
        ↓
GitHub PR Comment + Audit Log
```

---

## LLM Tiers

PR-Pilot supports three tiers. Choose based on your privacy and cost requirements:

| Tier | Models | Cost | Diff limit | Privacy |
|---|---|---|---|---|
| `free` | Groq + OpenRouter | Free | ~300 lines | Code sent to API |
| `paid` | Anthropic / OpenAI / Gemini | Pay per use | Unlimited | Code sent to API |
| `local` | Ollama (any model) | Free | Unlimited | Code never leaves your machine |

---

## Prerequisites

| Tool | Link |
|---|---|
| Docker Desktop | https://www.docker.com/products/docker-desktop |
| Git | https://git-scm.com |
| ngrok | https://ngrok.com/download |

Python 3.10+ is only needed if running without Docker.

---

## Quick Start (Docker)

### 1. Clone the repo

```bash
git clone https://github.com/your-username/pr-pilot.git
cd pr-pilot
```

### 2. Create a GitHub App

1. Go to **GitHub → Settings → Developer Settings → GitHub Apps → New GitHub App**
2. Fill in:
   - **App name**: PR-Pilot (or anything you like)
   - **Homepage URL**: `http://localhost:8000`
   - **Webhook URL**: leave blank for now
   - **Webhook secret**: generate a random string and save it
     ```bash
     # Mac/Linux
     openssl rand -hex 32
     # Windows PowerShell
     [System.Web.Security.Membership]::GeneratePassword(32,0)
     ```
3. Under **Permissions → Repository permissions** set:
   - Contents: Read
   - Issues: Read
   - Pull requests: Read and write
4. Under **Subscribe to events** check: **Pull request**
5. Click **Create GitHub App**
6. Note your **App ID** at the top of the settings page
7. Scroll to **Private keys → Generate a private key** — download the `.pem` file
8. Click **Install App** and install it on your target repository

### 3. Configure credentials

```bash
cp .env.example .env
mkdir -p secrets
mv ~/Downloads/your-app.private-key.pem secrets/github.pem
```

Edit `.env`:

```env
LLM_TIER=free

GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openai/gpt-4o-mini

GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=secrets/github.pem
GITHUB_INSTALLATION_ID=12345678
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

**Finding your Installation ID:**
Go to `https://github.com/settings/installations` → click Configure next to your app → the number in the URL is your installation ID.

**Free API keys:**
- Groq: https://console.groq.com
- OpenRouter: https://openrouter.ai

### 4. Start PR-Pilot

```bash
docker compose up --build
```

Wait for:
```
prpilot  | INFO:     Application startup complete.
prpilot  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. Start ngrok

In a separate terminal:

```bash
ngrok http 8000
```

You'll see:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

> **Important:** ngrok free plan generates a new URL every time you restart it.
> You must update your GitHub App webhook URL each time.

### 6. Connect GitHub App to your server

1. Go to `https://github.com/settings/apps/your-app-name`
2. Set **Webhook URL** to: `https://abc123.ngrok-free.app/webhook`
3. Click **Save changes**

### 7. Open a PR and test

Open a pull request on your connected repository. Within 60–120 seconds you should see a review comment posted automatically.

Check the dashboard at `http://localhost:8000/dashboard/` to see the review logged.

---

## LLM Tier Configuration

### Free Tier

```env
LLM_TIER=free
GROQ_API_KEY=your_key
OPENROUTER_API_KEY=your_key
```

Large PRs (200+ lines) are automatically truncated for the security scanner to stay within Groq's free tier token limits. The review comment will note when this happens. All other agents receive the full diff.

### Paid Tier

Full diff, no truncation, up to 3 concurrent reviews.

```env
LLM_TIER=paid
PAID_API_KEY=your_key
PAID_MODEL=claude-3-5-haiku-20241022
PAID_BASE_URL=https://api.anthropic.com/v1
```

Supported providers:

| Provider | Model | Base URL |
|---|---|---|
| Anthropic | `claude-3-5-haiku-20241022` | `https://api.anthropic.com/v1` |
| OpenAI | `gpt-4o-mini` | `https://api.openai.com/v1` |
| Gemini | `gemini-1.5-flash` | `https://generativelanguage.googleapis.com/v1beta` |

### Local Tier

Your code never leaves your machine. Requires Ollama.

```env
LLM_TIER=local
OLLAMA_MODEL=ollama/llama3.1
```

Start with Ollama:

```bash
docker compose --profile local up --build
```

Pull your model (first time only):

```bash
docker exec prpilot-ollama ollama pull llama3.1
```

> **Note:** Local tier runs on CPU by default. Reviews take 3–10 minutes.
> Uncomment the GPU section in `docker-compose.yml` for NVIDIA GPU acceleration.

---

## Dashboard

Visit `http://localhost:8000/dashboard/` after running your first review.

Shows per-review: repository, PR number, who opened it, branch, tech stack detected, verdict, confidence score, status, and duration. Click any run ID to see the full agent trace — every agent's reasoning, what Semgrep returned, what the verifier filtered.

---

## Project Structure

```
pr-pilot/
├── src/prtool/
│   ├── api.py                 — FastAPI webhook handler, concurrency control
│   ├── crew.py                — CrewAI 6-agent pipeline
│   ├── schemas.py             — Pydantic models with graceful coercion
│   ├── audit_logger.py        — SQLite audit logging
│   ├── dashboard.py           — Dashboard HTML + JSON API routes
│   ├── config/
│   │   ├── agents.yaml        — Agent roles, goals, and anti-hallucination rules
│   │   └── tasks.yaml         — Task descriptions and expected outputs
│   ├── tools/
│   │   ├── semgrep_tool.py    — Semgrep SAST wrapper (UTF-8 safe, Windows compatible)
│   │   └── merge_sim_tool.py  — Git merge simulation tool
│   └── utils/
│       └── github_manager.py  — GitHub App auth + PR data fetching
├── secrets/                   — GitHub App private key (gitignored)
├── Dockerfile.app             — FastAPI app container
├── docker-compose.yml         — Full stack (bot + Ollama optional)
├── .env.example               — Environment variable template
└── pyproject.toml             — Python project config (crewai, fastapi, pygithub)
```

---

## Running Without Docker

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
.venv\Scripts\activate         # Windows

# Install dependencies
pip install uv
uv sync

# Install semgrep (required for security scanning)
pip install semgrep

# Start the server
uvicorn prtool.api:app --reload --port 8000
```

Ensure `git` is on your PATH — required for merge simulation.

---

## Common Issues

**Webhook not triggering**
- Confirm ngrok is running and the forwarding URL in GitHub App settings ends with `/webhook`
- ngrok free plan gives a new URL on every restart — always update GitHub App settings after restarting ngrok
- Check logs: `docker compose logs -f prpilot`

**401 Bad credentials on startup**
- The `GITHUB_PRIVATE_KEY_PATH` in `.env` doesn't match where your `.pem` file actually is
- The key was regenerated on GitHub — download the new one and replace `secrets/github.pem`

**413 Request too large**
- Expected on free tier for large PRs — diff is automatically truncated
- Switch to `LLM_TIER=paid` for unlimited diff size

**Review comment says "partial review" on large PRs**
- The diff exceeded the free tier limit and was truncated
- The bot is being honest — upgrade tier for full analysis

**Dashboard shows 0 reviews after switching to Docker**
- Docker uses an internal volume for the database, separate from your local `prpilot_audit.db`
- To keep existing data, mount your local file in `docker-compose.yml`:
  ```yaml
  volumes:
    - ./prpilot_audit.db:/app/data/prpilot_audit.db
    - ./secrets:/app/secrets:ro
  ```

**Semgrep Unicode error on Windows**
- Already fixed — `semgrep_tool.py` forces `encoding="utf-8"` on subprocess output

---

## Contributing

Contributions welcome. The highest-impact areas:

- **Prompt improvements** — `agents.yaml` and `tasks.yaml` are where review quality lives. Better mechanical description rules, tighter anti-hallucination constraints, and improved verdict calibration all make a real difference.
- **Language/framework detection** — `_detect_tech_stack()` in `api.py` uses string matching. More framework patterns (Laravel, Spring Boot, FastAPI, etc.) improve the context the diff reviewer gets.
- **New tool integrations** — the agent pipeline is modular. A Bandit tool, a dependency audit tool, or a test coverage tool can be added as a new CrewAI tool without touching existing agents.
- **Dashboard improvements** — the dashboard is plain HTML/CSS in `dashboard.py`. PR filtering, search, and trend charts would be useful additions.

---

## License

MIT