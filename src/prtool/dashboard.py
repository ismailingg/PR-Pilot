"""
dashboard.py — PR-Pilot audit dashboard, v3
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from prtool.audit_logger import get_recent_runs, get_run_by_id, get_agent_logs_for_run, get_stats

dashboard_router = APIRouter(prefix="/dashboard")

# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------

@dashboard_router.get("/runs")
def list_runs(limit: int = 20):
    return get_recent_runs(limit)

@dashboard_router.get("/runs/{run_id}")
def get_run(run_id: str):
    run = get_run_by_id(run_id)
    if not run:
        return {"error": "Run not found"}
    logs = get_agent_logs_for_run(run_id)
    return {"run": run, "agent_logs": logs}

@dashboard_router.get("/stats")
def stats():
    return get_stats()

# ---------------------------------------------------------------------------
# Verdict / status metadata
# ---------------------------------------------------------------------------

VERDICT_META = {
    "strongly_recommend_merge": ("green",  "Merge"),
    "merge":                    ("green",  "Merge"),
    "merge_with_suggestions":   ("amber",  "Suggestions"),
    "merge_with_advice":        ("amber",  "Suggestions"),
    "approve_with_minor_changes":("amber", "Suggestions"),
    "needs_work":               ("orange", "Needs Work"),
    "needs_human_review":       ("orange", "Needs Work"),
    "do_not_merge":             ("red",    "Block"),
    "block":                    ("red",    "Block"),
    "unknown":                  ("gray",   "Unknown"),
    "failed":                   ("red",    "Failed"),
}

VERDICT_COLORS = {
    "green":  ("background:#EAF3DE;color:#3B6D11",  "#639922"),
    "amber":  ("background:#FAEEDA;color:#854F0B",  "#EF9F27"),
    "orange": ("background:#FEF0E6;color:#854F0B",  "#F97316"),
    "red":    ("background:#FCEBEB;color:#A32D2D",  "#E24B4A"),
    "gray":   ("background:#F1EFE8;color:#5F5E5A",  "#888780"),
}

STATUS_COLORS = {
    "completed": "#639922",
    "started":   "#EF9F27",
    "failed":    "#E24B4A",
}

def _chip(verdict: str) -> str:
    ramp, label = VERDICT_META.get(verdict, ("gray", verdict or "Unknown"))
    style, _ = VERDICT_COLORS.get(ramp, VERDICT_COLORS["gray"])
    return (
        f'<span style="{style};padding:2px 9px;border-radius:20px;'
        f'font-size:11px;font-weight:500;white-space:nowrap">{label}</span>'
    )

def _dot(status: str) -> str:
    color = STATUS_COLORS.get(status, "#888780")
    return f'<span style="width:7px;height:7px;border-radius:50%;background:{color};display:inline-block" title="{status}"></span>'

def _sidebar_dot(verdict: str) -> str:
    ramp, _ = VERDICT_META.get(verdict, ("gray", ""))
    _, color = VERDICT_COLORS.get(ramp, VERDICT_COLORS["gray"])
    return f'<span style="width:8px;height:8px;border-radius:50%;background:{color};display:inline-block;margin-right:7px"></span>'

def _avatar(username: str) -> str:
    if not username or username == "unknown" or username == "None":
        return ""
    initials = (username[:2]).upper()
    return (
        f'<div style="display:inline-flex;align-items:center;gap:5px;'
        f'background:#F1EFE8;border:0.5px solid #D3D1C7;'
        f'border-radius:20px;padding:2px 8px 2px 2px;font-size:11px;color:#5F5E5A">'
        f'<div style="width:16px;height:16px;border-radius:50%;background:#B5D4F4;'
        f'color:#0C447C;display:flex;align-items:center;justify-content:center;'
        f'font-size:9px;font-weight:500">{initials}</div>'
        f'{username}</div>'
    )

# ---------------------------------------------------------------------------
# Main dashboard HTML
# ---------------------------------------------------------------------------

@dashboard_router.get("/", response_class=HTMLResponse)
def dashboard_html():
    runs = get_recent_runs(50)
    s    = get_stats()

    avg_conf = s.get("avg_confidence", 0)

    # Sidebar verdict breakdown
    breakdown_html = ""
    for v, count in s.get("verdict_breakdown", {}).items():
        _, label = VERDICT_META.get(v, ("gray", v or "Unknown"))
        dot = _sidebar_dot(v)
        breakdown_html += (
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding:5px 0;border-bottom:0.5px solid #F1EFE8">'
            f'<span style="display:flex;align-items:center;font-size:12px;color:#5F5E5A">'
            f'{dot}{label}</span>'
            f'<span style="font-size:12px;font-weight:500;color:#2C2C2A">{count}</span>'
            f'</div>'
        )
    if not breakdown_html:
        breakdown_html = '<p style="font-size:12px;color:#888780;margin-top:6px">No data yet</p>'

    # Table rows
    rows = ""
    for r in runs:
        conf    = f"{round(r['confidence'] * 100)}%" if r.get("confidence") else "—"
        dur     = f"{r['duration_seconds']:.1f}s" if r.get("duration_seconds") else "—"
        branch  = r.get("pr_branch") or "—"
        started = (r.get("started_at") or "")[:16].replace("T", " ")
        author  = r.get("pr_author") or ""
        repo    = r.get("repo_name", "").split("/")[-1]   # just repo name, not owner/repo

        rows += f"""
        <tr onmouseover="this.style.background='#F8F7F4'" onmouseout="this.style.background=''">
          <td style="font-family:monospace;font-size:11px">
            <a href="/dashboard/runs/{r['run_id']}" style="color:#185FA5;text-decoration:none">{r['run_id'][:8]}</a>
          </td>
          <td style="font-weight:500;color:#2C2C2A">{repo}</td>
          <td style="color:#888780">#{r['pr_number']}</td>
          <td>{_avatar(author) if author else '<span style="color:#B4B2A9;font-size:12px">—</span>'}</td>
          <td>{_chip(r.get('verdict','unknown'))}</td>
          <td style="font-family:monospace;font-size:12px;font-weight:500;color:#2C2C2A">{conf}</td>
          <td style="text-align:center">{_dot(r.get('status','unknown'))}</td>
          <td style="color:#B4B2A9;font-size:12px;text-align:right">{dur}</td>
          <td style="color:#B4B2A9;font-size:12px">{started}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="9" style="padding:32px;text-align:center;color:#B4B2A9;font-size:13px">No reviews yet — open a PR to get started.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PR-Pilot</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{
      font-family:'Inter',system-ui,sans-serif;
      background:#F1EFE8;
      color:#2C2C2A;
      min-height:100vh;
      font-size:13px;
      line-height:1.5;
    }}
    .topbar {{
      background:#fff;
      border-bottom:0.5px solid #D3D1C7;
      padding:0 24px;
      height:52px;
      display:flex;
      align-items:center;
      justify-content:space-between;
    }}
    .brand {{ display:flex;align-items:center;gap:10px; }}
    .brand-icon {{
      width:28px;height:28px;
      background:#185FA5;
      border-radius:7px;
      display:flex;align-items:center;justify-content:center;
      color:#fff;font-size:13px;font-weight:500;
    }}
    .brand-name {{ font-size:14px;font-weight:500;color:#2C2C2A; }}
    .brand-sub  {{ font-size:11px;color:#888780;margin-top:1px; }}
    .live {{
      display:flex;align-items:center;gap:6px;
      font-size:11px;color:#888780;
    }}
    .live-dot {{
      width:6px;height:6px;border-radius:50%;background:#639922;
      animation:pulse 2s infinite;
    }}
    @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}
    .layout {{ display:flex;min-height:calc(100vh - 52px); }}
    .sidebar {{
      width:210px;min-width:210px;
      background:#fff;
      border-right:0.5px solid #D3D1C7;
      padding:22px 18px;
    }}
    .stat {{ margin-bottom:18px; }}
    .stat-val {{
      font-size:30px;font-weight:500;
      font-family:'JetBrains Mono',monospace;
      line-height:1;color:#2C2C2A;
    }}
    .stat-label {{
      font-size:10px;color:#888780;
      text-transform:uppercase;letter-spacing:0.07em;
      margin-top:3px;font-weight:500;
    }}
    .divider {{ border:none;border-top:0.5px solid #D3D1C7;margin:16px 0; }}
    .section-label {{
      font-size:10px;color:#B4B2A9;
      text-transform:uppercase;letter-spacing:0.09em;
      font-weight:500;margin-bottom:8px;
    }}
    .main {{ flex:1;padding:22px 24px;overflow-x:auto; }}
    .page-title {{ font-size:15px;font-weight:500;color:#2C2C2A;margin-bottom:2px; }}
    .page-sub   {{ font-size:12px;color:#888780;margin-bottom:20px; }}
    table {{ width:100%;border-collapse:collapse;font-size:12px;background:#fff;
             border-radius:8px;overflow:hidden;border:0.5px solid #D3D1C7; }}
    thead tr {{ border-bottom:0.5px solid #D3D1C7;background:#F8F7F4; }}
    th {{
      text-align:left;padding:9px 12px;
      font-size:10px;text-transform:uppercase;
      letter-spacing:0.08em;color:#888780;font-weight:500;
    }}
    td {{ padding:10px 12px;border-bottom:0.5px solid #F1EFE8;vertical-align:middle; }}
    tr:last-child td {{ border-bottom:none; }}
    a {{ text-decoration:none; }}
  </style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <div class="brand-icon">P</div>
    <div>
      <div class="brand-name">PR-Pilot</div>
      <div class="brand-sub">Review dashboard</div>
    </div>
  </div>
  <div class="live"><div class="live-dot"></div>Live</div>
</header>

<div class="layout">
  <aside class="sidebar">
    <div class="stat">
      <div class="stat-val">{s.get('total_reviews',0)}</div>
      <div class="stat-label">Total reviews</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:#3B6D11">{s.get('completed',0)}</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:#A32D2D">{s.get('failed',0)}</div>
      <div class="stat-label">Failed</div>
    </div>
    <div class="stat">
      <div class="stat-val">{avg_conf}%</div>
      <div class="stat-label">Avg confidence</div>
    </div>
    <hr class="divider">
    <div class="section-label">Verdicts</div>
    {breakdown_html}
  </aside>

  <main class="main">
    <div class="page-title">Review history</div>
    <div class="page-sub">All PR reviews across connected repositories</div>

    <table>
      <thead>
        <tr>
          <th>Run</th>
          <th>Repository</th>
          <th>PR</th>
          <th>Author</th>
          <th>Verdict</th>
          <th>Conf</th>
          <th style="text-align:center">Status</th>
          <th style="text-align:right">Duration</th>
          <th>Started</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </main>
</div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Run detail page
# ---------------------------------------------------------------------------

@dashboard_router.get("/runs/{run_id}/html", response_class=HTMLResponse)
def run_detail_html(run_id: str):
    run = get_run_by_id(run_id)
    if not run:
        return HTMLResponse("<h1 style='font-family:sans-serif;padding:32px'>Run not found</h1>", status_code=404)

    logs  = get_agent_logs_for_run(run_id)
    conf  = f"{round(run['confidence'] * 100)}%" if run.get("confidence") else "—"
    ramp, label = VERDICT_META.get(run.get("verdict",""), ("gray","—"))
    chip_style, dot_color = VERDICT_COLORS.get(ramp, VERDICT_COLORS["gray"])

    steps_html = ""
    for log in logs:
        output  = (log.get("output") or "")[:3000]
        status  = log.get("status", "completed")
        sc      = STATUS_COLORS.get(status, "#888780")
        steps_html += f"""
      <div style="margin-bottom:10px;border:0.5px solid #D3D1C7;border-radius:8px;overflow:hidden">
        <div style="display:flex;align-items:center;justify-content:space-between;
                    padding:10px 14px;background:#F8F7F4;border-bottom:0.5px solid #D3D1C7">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="width:7px;height:7px;border-radius:50%;background:{sc};display:inline-block"></span>
            <span style="font-weight:500;color:#2C2C2A;font-size:12px">{log['agent_name']}</span>
          </div>
          <span style="color:#888780;font-size:11px;font-family:'JetBrains Mono',monospace">{log['task_name']}</span>
        </div>
        <pre style="padding:14px;font-family:'JetBrains Mono',monospace;font-size:11px;
                    color:#5F5E5A;overflow-x:auto;white-space:pre-wrap;
                    background:#fff;line-height:1.6;max-height:280px;overflow-y:auto">{output}</pre>
      </div>"""

    error_block = ""
    if run.get("error_message"):
        error_block = f"""
      <div style="background:#FCEBEB;border:0.5px solid #F09595;border-radius:8px;
                  padding:12px 14px;margin-bottom:16px;font-size:12px;color:#A32D2D">
        <strong>Error:</strong> {run['error_message']}
      </div>"""

    meta_items = [
        ("Repository",    run["repo_name"]),
        ("Pull Request",  f"#{run['pr_number']}"),
        ("Opened by",     run.get("pr_author") or "—"),
        ("Branch",        run.get("pr_branch") or "—"),
        ("Tech Stack",    run.get("tech_stack") or "—"),
        ("Verdict",       f'<span style="{chip_style};padding:2px 9px;border-radius:20px;font-size:11px;font-weight:500">{label}</span>'),
        ("Confidence",    conf),
        ("Status",        run.get("status","—")),
        ("Duration",      f"{run.get('duration_seconds','—')}s"),
        ("Started",       (run.get("started_at","")[:19]).replace("T"," ")),
        ("Comment posted",("Yes" if run.get("comment_posted") else "No")),
    ]

    meta_html = ""
    for key, val in meta_items:
        meta_html += f"""
        <div style="background:#fff;padding:12px 14px">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;
                      color:#888780;font-weight:500;margin-bottom:3px">{key}</div>
          <div style="font-size:13px;font-weight:500;color:#2C2C2A">{val}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Run {run_id[:8]} — PR-Pilot</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Inter',system-ui,sans-serif;background:#F1EFE8;
          color:#2C2C2A;padding:28px;font-size:13px;line-height:1.5}}
    a{{color:#185FA5;text-decoration:none}}
    a:hover{{color:#0C447C}}
    h1{{font-size:17px;font-weight:500;color:#2C2C2A;margin-bottom:16px;
        font-family:'JetBrains Mono',monospace}}
    h2{{font-size:10px;text-transform:uppercase;letter-spacing:0.08em;
        color:#888780;font-weight:500;margin:20px 0 10px}}
  </style>
</head>
<body>
  <a href="/dashboard/" style="font-size:12px;color:#888780;display:inline-flex;align-items:center;gap:4px;margin-bottom:18px">
    ← All reviews
  </a>
  <h1>{run_id[:8]}...</h1>

  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
              gap:1px;background:#D3D1C7;border-radius:8px;overflow:hidden;margin-bottom:20px">
    {meta_html}
  </div>

  {error_block}

  <h2>Agent trace — {len(logs)} steps</h2>
  {steps_html if steps_html else '<p style="color:#B4B2A9;padding:20px 0">No agent steps recorded.</p>'}
</body>
</html>"""
    return html