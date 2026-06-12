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

An automated GitHub PR review bot powered by a multi-agent AI pipeline. PR-Pilot reviews your pull requests and posts structured feedback directly as GitHub comments — covering code quality, security findings, and merge compatibility.

![Dashboard](https://img.shields.io/badge/dashboard-localhost%3A8000%2Fdashboard-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What It Does

When a PR is opened or updated on a connected repository, PR-Pilot:

1. Fetches the diff and linked issue from GitHub
2. Extracts the intent and acceptance criteria
3. Reviews the code diff mechanically — not just the description
4. Runs Semgrep static analysis for security issues
5. Simulates a git merge to detect conflicts before they happen
6. Posts a structured review comment with a verdict, confidence score, and findings
7. Logs every review to a local SQLite database viewable on a dashboard

---

## Prerequisites

Install these before anything else:

| Tool | Version | Link |
|---|---|---|
| Docker Desktop | Latest | https://www.docker.com/products/docker-desktop |
| Git | Any | https://git-scm.com |
| ngrok | Latest | https://ngrok.com/download |
| Python | 3.10–3.13 | https://python.org (only needed for local dev without Docker) |

---

## Quick Start (Docker — Recommended)

### 1. Clone the repo

```bash
git clone https://github.com/your-username/pr-pilot.git
cd pr-pilot
```

### 2. Create your GitHub App

1. Go to **GitHub → Settings → Developer Settings → GitHub Apps → New GitHub App**
2. Fill in:
   - **App name**: PR-Pilot (or anything you like)
   - **Homepage URL**: `http://localhost:8000`
   - **Webhook URL**: leave blank for now — you'll fill this after ngrok starts
   - **Webhook secret**: generate a random string, e.g. `openssl rand -hex 32` — save it
3. Under **Permissions → Repository permissions**, set:
   - Contents: Read
   - Issues: Read
   - Pull requests: Read and write
4. Under **Subscribe to events**, check: **Pull request**
5. Click **Create GitHub App**
6. Note your **App ID** (shown at the top of the app settings page)
7. Scroll to **Private keys** → **Generate a private key** → download the `.pem` file
8. Go to **Install App** → install it on your repo

### 3. Set up credentials

```bash
# Copy the example env file
cp .env.example .env

# Create secrets folder and move your private key there
mkdir -p secrets
mv ~/Downloads/your-app-name.pem secrets/github.pem
```

Edit `.env` and fill in your values:

```env
# LLM tier — choose one
LLM_TIER=free

# Free tier keys (get at console.groq.com and openrouter.ai)
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openai/gpt-4o-mini

# GitHub App credentials
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=secrets/github.pem
GITHUB_INSTALLATION_ID=12345678
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

**Finding your Installation ID:**
Go to `https://github.com/settings/installations` — click Configure next to your app. The number in the URL is your installation ID.

### 4. Start ngrok

In a terminal, start the tunnel:

```bash
ngrok http 8000
```

You'll see a line like:

```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

Copy the `https://` URL. Keep this terminal open.

### 5. Update your GitHub App webhook URL

1. Go back to your GitHub App settings: `https://github.com/settings/apps/your-app-name`
2. Set **Webhook URL** to: `https://abc123.ngrok-free.app/webhook`
3. Click **Save changes**

### 6. Start PR-Pilot

```bash
docker compose up --build
```

Wait for:
```
prpilot  | INFO:     Application startup complete.
prpilot  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 7. Test it

Open a pull request on your connected repository. Within a minute you should see:
- A review comment posted to the PR on GitHub
- The review appearing on the dashboard at `http://localhost:8000/dashboard/`

---

## LLM Tiers

PR-Pilot supports three tiers. Set `LLM_TIER` in your `.env`:

### Free Tier (default)
Uses Groq + OpenRouter free API keys. No cost.

```env
LLM_TIER=free
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
```

Get free keys:
- Groq: https://console.groq.com
- OpenRouter: https://openrouter.ai

**Limitation:** Diffs larger than ~300 lines are truncated due to Groq's free tier token limits. The review comment will note when this happens.

### Paid Tier
Uses a single paid API key. Full diff analysis, no truncation.

```env
LLM_TIER=paid
PAID_API_KEY=your_key
PAID_MODEL=claude-3-5-haiku-20241022
PAID_BASE_URL=https://api.anthropic.com/v1
```

Supported providers:

| Provider | Model example | Base URL |
|---|---|---|
| Anthropic | `claude-3-5-haiku-20241022` | `https://api.anthropic.com/v1` |
| OpenAI | `gpt-4o-mini` | `https://api.openai.com/v1` |
| Google Gemini | `gemini-1.5-flash` | `https://generativelanguage.googleapis.com/v1beta` |

### Local Tier (fully private)
Uses Ollama running on your machine. Your code never leaves your network.

```env
LLM_TIER=local
OLLAMA_MODEL=ollama/llama3.1
```

Start with Ollama included:

```bash
docker compose --profile local up --build
```

Then pull your model (first time only):

```bash
docker exec prpilot-ollama ollama pull llama3.1
```

**Note:** Local tier runs on CPU by default. Reviews will take 3–10 minutes depending on your hardware. Uncomment the GPU section in `docker-compose.yml` if you have an NVIDIA GPU.

---

## Dashboard

Visit `http://localhost:8000/dashboard/` to see all review history.

Features:
- Total reviews, completed, failed, average confidence
- Verdict breakdown (Merge / Suggestions / Block)
- Per-review: repo, PR number, author, branch, tech stack, verdict, confidence, status, duration
- Click any run ID to see the full agent trace — what each agent said and why

---

## Project Structure

```
pr-pilot/
├── src/prtool/
│   ├── api.py              — FastAPI webhook handler
│   ├── crew.py             — CrewAI agent pipeline
│   ├── schemas.py          — Pydantic models
│   ├── audit_logger.py     — SQLite logging
│   ├── dashboard.py        — Dashboard routes and HTML
│   ├── config/
│   │   ├── agents.yaml     — Agent definitions and prompts
│   │   └── tasks.yaml      — Task definitions
│   ├── tools/
│   │   ├── semgrep_tool.py — Semgrep SAST wrapper
│   │   └── merge_sim_tool.py — Git merge simulation
│   └── utils/
│       └── github_manager.py — GitHub API client
├── secrets/                — GitHub App private key (gitignored)
├── Dockerfile.app          — FastAPI app container
├── docker-compose.yml      — Full stack definition
├── .env.example            — Environment variable template
└── pyproject.toml          — Python project config
```

---

## Running Without Docker (Local Development)

```bash
# Install uv
pip install uv

# Install dependencies
uv sync

# Start the server
uvicorn prtool.api:app --reload --port 8000
```

Make sure `semgrep` is also installed:

```bash
pip install semgrep
```

And `git` is available on your PATH for merge simulation.

---

## Common Issues

**Webhook not triggering**
- Check ngrok is running and the URL in your GitHub App settings matches
- ngrok free plan generates a new URL every restart — update GitHub App settings each time
- Check Docker logs: `docker compose logs -f prpilot`

**401 Bad credentials**
- Your GitHub App private key path in `.env` is wrong
- The private key file has been regenerated on GitHub — download a new one

**413 Request too large (free tier)**
- Normal for large PRs on free tier — diff is automatically truncated
- Switch to `LLM_TIER=paid` for full diff analysis

**Dashboard shows 0 reviews after switching to Docker**
- Docker uses a separate database volume from your local `prpilot_audit.db`
- To use your existing data, add this to `docker-compose.yml` under `prpilot` volumes:
  ```yaml
  - ./prpilot_audit.db:/app/data/prpilot_audit.db
  ```

**Semgrep Unicode error on Windows**
- Fixed in the current version — `semgrep_tool.py` uses `encoding="utf-8"` explicitly

---

## Agent Pipeline

```
PR opened/updated
      ↓
Intent Extractor   — reads PR description and linked issue, extracts acceptance criteria
      ↓
Diff Reviewer      — reviews changed code mechanically, line by line
      ↓
Security Scanner   — runs Semgrep SAST, interprets findings
      ↓
Merge Sim Engineer — simulates git merge, detects conflicts
      ↓
Verifier           — cross-references findings against intent, filters false positives
      ↓
Decider            — writes the final GitHub comment with verdict and confidence score
      ↓
GitHub PR Comment
```

---

## Contributing

Issues and PRs welcome. The prompts in `agents.yaml` and `tasks.yaml` are the most impactful place to improve review quality.

---

## License

MIT