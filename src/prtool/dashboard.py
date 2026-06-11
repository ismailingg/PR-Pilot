"""
dashboard.py — PR-Pilot audit dashboard, v2
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
# HTML dashboard
# ---------------------------------------------------------------------------

VERDICT_META = {
    "strongly_recommend_merge": ("#10b981", "Merge"),
    "merge":                    ("#10b981", "Merge"),
    "merge_with_suggestions":   ("#f59e0b", "Merge w/ Notes"),
    "merge_with_advice":        ("#f59e0b", "Merge w/ Notes"),
    "needs_work":               ("#f97316", "Needs Work"),
    "needs_human_review":       ("#f97316", "Needs Work"),
    "do_not_merge":             ("#ef4444", "Block"),
    "block":                    ("#ef4444", "Block"),
    "unknown":                  ("#475569", "Unknown"),
    "failed":                   ("#ef4444", "Failed"),
}

STATUS_META = {
    "completed": ("#10b981", "●"),
    "started":   ("#f59e0b", "◌"),
    "failed":    ("#ef4444", "✕"),
}

def _verdict_chip(verdict: str) -> str:
    color, label = VERDICT_META.get(verdict, ("#475569", verdict or "—"))
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:{color}18;color:{color};border:1px solid {color}40;'
        f'padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;'
        f'letter-spacing:0.04em;white-space:nowrap">{label}</span>'
    )

def _status_dot(status: str) -> str:
    color, sym = STATUS_META.get(status, ("#475569", "?"))
    return f'<span style="color:{color};font-size:13px" title="{status}">{sym}</span>'

@dashboard_router.get("/", response_class=HTMLResponse)
def dashboard_html():
    runs  = get_recent_runs(50)
    s     = get_stats()

    # Build verdict breakdown pills
    breakdown_html = ""
    for v, count in s.get("verdict_breakdown", {}).items():
        color, label = VERDICT_META.get(v, ("#475569", v))
        breakdown_html += (
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding:6px 0;border-bottom:1px solid #1e293b">'
            f'<span style="color:{color};font-size:12px;font-weight:500">{label}</span>'
            f'<span style="color:#f1f5f9;font-weight:700;font-size:13px">{count}</span>'
            f'</div>'
        )
    if not breakdown_html:
        breakdown_html = '<p style="color:#475569;font-size:12px;margin:8px 0">No data yet</p>'

    # Build rows
    rows = ""
    for r in runs:
        conf    = f"{round(r['confidence'] * 100)}%" if r.get("confidence") else "—"
        dur_raw = r.get("duration_seconds")
        dur     = f"{dur_raw:.1f}s" if dur_raw else "—"
        branch  = r.get("pr_branch") or "—"
        started = (r.get("started_at") or "")[:16].replace("T", " ")
        rows += f"""
        <tr class="row">
          <td><a href="/dashboard/runs/{r['run_id']}" class="run-link">{r['run_id'][:8]}</a></td>
          <td style="color:#cbd5e1">{r['repo_name']}</td>
          <td style="color:#94a3b8">#{r['pr_number']}</td>
          <td style="color:#94a3b8;font-family:'JetBrains Mono',monospace;font-size:11px">{r.get('pr_author','—')}</td>
          <td style="color:#64748b;font-size:12px">{branch}</td>
          <td style="color:#64748b;font-size:12px">{r.get('tech_stack','—')}</td>
          <td>{_verdict_chip(r.get('verdict','unknown'))}</td>
          <td style="color:#f1f5f9;font-weight:600;text-align:right">{conf}</td>
          <td style="text-align:center">{_status_dot(r.get('status','unknown'))}</td>
          <td style="color:#475569;font-size:12px;text-align:right">{dur}</td>
          <td style="color:#475569;font-size:12px">{started}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="11" style="padding:40px;text-align:center;color:#334155">No reviews yet — open a PR to get started.</td></tr>'

    avg_conf = s.get('avg_confidence', 0)
    conf_color = "#10b981" if avg_conf >= 80 else "#f59e0b" if avg_conf >= 60 else "#ef4444"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PR-Pilot</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #080d14;
      --surface:   #0d1520;
      --border:    #1a2535;
      --text:      #e2e8f0;
      --muted:     #475569;
      --accent:    #3b82f6;
      --accent-dim:#1d3a6e;
    }}

    body {{
      font-family: 'Inter', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      font-size: 13px;
      line-height: 1.5;
    }}

    /* ── Top bar ── */
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 28px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    .logo {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .logo-mark {{
      width: 28px; height: 28px;
      background: var(--accent);
      border-radius: 7px;
      display: flex; align-items: center; justify-content: center;
      font-size: 14px; font-weight: 700; color: #fff;
    }}
    .logo-text {{
      font-weight: 600;
      font-size: 14px;
      color: #f8fafc;
      letter-spacing: -0.01em;
    }}
    .logo-sub {{
      font-size: 11px;
      color: var(--muted);
      font-weight: 400;
    }}
    .live-dot {{
      display: flex; align-items: center; gap: 6px;
      font-size: 11px; color: var(--muted);
    }}
    .live-dot::before {{
      content: '';
      width: 6px; height: 6px;
      background: #10b981;
      border-radius: 50%;
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50%       {{ opacity: 0.3; }}
    }}

    /* ── Layout ── */
    .layout {{
      display: grid;
      grid-template-columns: 220px 1fr;
      min-height: calc(100vh - 57px);
    }}

    /* ── Sidebar ── */
    .sidebar {{
      border-right: 1px solid var(--border);
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }}
    .stat-block {{ padding: 0 4px; }}
    .stat-number {{
      font-size: 36px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      line-height: 1;
      letter-spacing: -0.03em;
    }}
    .stat-label {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      margin-top: 4px;
      font-weight: 500;
    }}
    .divider {{
      border: none;
      border-top: 1px solid var(--border);
    }}
    .section-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      font-weight: 600;
      padding: 0 4px;
      margin-bottom: 6px;
    }}

    /* ── Main ── */
    .main {{ padding: 24px 28px; overflow-x: auto; }}
    .page-title {{
      font-size: 15px;
      font-weight: 600;
      color: #f8fafc;
      margin-bottom: 4px;
    }}
    .page-sub {{
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 20px;
    }}

    /* ── Table ── */
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    thead tr {{
      border-bottom: 1px solid var(--border);
    }}
    th {{
      text-align: left;
      padding: 8px 12px;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      font-weight: 600;
      white-space: nowrap;
    }}
    th:last-child, td:last-child {{ text-align: right; padding-right: 0; }}
    .row td {{
      padding: 11px 12px;
      border-bottom: 1px solid #111a27;
      vertical-align: middle;
    }}
    .row:hover td {{ background: #0d1a2a; }}
    .run-link {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: var(--accent);
      text-decoration: none;
      font-weight: 500;
    }}
    .run-link:hover {{ color: #93c5fd; }}
  </style>
</head>
<body>

<header class="topbar">
  <div class="logo">
    <div class="logo-mark">P</div>
    <div>
      <div class="logo-text">PR-Pilot</div>
      <div class="logo-sub">Review dashboard</div>
    </div>
  </div>
  <div class="live-dot">Live</div>
</header>

<div class="layout">

  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="stat-block">
      <div class="stat-number" style="color:#f8fafc">{s.get('total_reviews', 0)}</div>
      <div class="stat-label">Total reviews</div>
    </div>

    <div class="stat-block">
      <div class="stat-number" style="color:#10b981">{s.get('completed', 0)}</div>
      <div class="stat-label">Completed</div>
    </div>

    <div class="stat-block">
      <div class="stat-number" style="color:#ef4444">{s.get('failed', 0)}</div>
      <div class="stat-label">Failed</div>
    </div>

    <div class="stat-block">
      <div class="stat-number" style="color:{conf_color}">{avg_conf}%</div>
      <div class="stat-label">Avg confidence</div>
    </div>

    <hr class="divider">

    <div>
      <div class="section-label">Verdicts</div>
      {breakdown_html}
    </div>
  </aside>

  <!-- Main content -->
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
          <th>Branch</th>
          <th>Stack</th>
          <th>Verdict</th>
          <th style="text-align:right">Conf</th>
          <th style="text-align:center">Status</th>
          <th style="text-align:right">Duration</th>
          <th>Started</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </main>

</div>
</body>
</html>"""
    return html


@dashboard_router.get("/runs/{run_id}/html", response_class=HTMLResponse)
def run_detail_html(run_id: str):
    run = get_run_by_id(run_id)
    if not run:
        return HTMLResponse("<h1>Run not found</h1>", status_code=404)

    logs  = get_agent_logs_for_run(run_id)
    conf  = f"{round(run['confidence'] * 100)}%" if run.get("confidence") else "—"
    color, label = VERDICT_META.get(run.get("verdict",""), ("#475569","—"))

    steps_html = ""
    for i, log in enumerate(logs):
        output  = (log.get("output") or "")[:3000]
        status  = log.get("status","completed")
        sc, _   = STATUS_META.get(status, ("#475569","?"))
        steps_html += f"""
    <div style="margin-bottom:12px;border:1px solid #1a2535;border-radius:8px;overflow:hidden">
      <div style="display:flex;align-items:center;justify-content:space-between;
                  padding:10px 14px;background:#0d1520;border-bottom:1px solid #1a2535">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="color:{sc};font-size:10px">●</span>
          <span style="font-weight:600;color:#f1f5f9;font-size:12px">{log['agent_name']}</span>
        </div>
        <span style="color:#475569;font-size:11px;font-family:'JetBrains Mono',monospace">{log['task_name']}</span>
      </div>
      <pre style="padding:14px;font-family:'JetBrains Mono',monospace;font-size:11px;
                  color:#94a3b8;overflow-x:auto;white-space:pre-wrap;
                  background:#080d14;line-height:1.6;max-height:300px;overflow-y:auto">{output}</pre>
    </div>"""

    error_block = ""
    if run.get("error_message"):
        error_block = f"""
    <div style="background:#1c0a0a;border:1px solid #7f1d1d;border-radius:8px;
                padding:14px;margin-bottom:20px;font-size:12px;color:#fca5a5">
      <strong>Error:</strong> {run['error_message']}
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Run {run_id[:8]} — PR-Pilot</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Inter',system-ui,sans-serif; background:#080d14; color:#e2e8f0;
            padding:28px; font-size:13px; line-height:1.5; }}
    a {{ color:#3b82f6; text-decoration:none; }}
    a:hover {{ color:#93c5fd; }}
    .back {{ font-size:12px; color:#475569; display:inline-flex; align-items:center;
             gap:4px; margin-bottom:20px; }}
    .back:hover {{ color:#94a3b8; }}
    h1 {{ font-size:18px; font-weight:700; color:#f8fafc; margin-bottom:16px;
          font-family:'JetBrains Mono',monospace; }}
    .meta-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
                  gap:1px; background:#1a2535; border-radius:10px; overflow:hidden;
                  margin-bottom:24px; }}
    .meta-cell {{ background:#0d1520; padding:14px 16px; }}
    .meta-key {{ font-size:10px; text-transform:uppercase; letter-spacing:0.08em;
                 color:#475569; font-weight:600; margin-bottom:4px; }}
    .meta-val {{ font-size:13px; font-weight:600; color:#f1f5f9; }}
    h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:0.08em;
          color:#475569; font-weight:600; margin-bottom:14px; }}
  </style>
</head>
<body>
  <a class="back" href="/dashboard/">← All reviews</a>
  <h1>{run_id[:8]}...</h1>

  <div class="meta-grid">
    <div class="meta-cell"><div class="meta-key">Repository</div><div class="meta-val">{run['repo_name']}</div></div>
    <div class="meta-cell"><div class="meta-key">Pull Request</div><div class="meta-val">#{run['pr_number']}</div></div>
    <div class="meta-cell"><div class="meta-key">Opened by</div><div class="meta-val" style="font-family:'JetBrains Mono',monospace;font-size:12px">{run.get('pr_author','—')}</div></div>
    <div class="meta-cell"><div class="meta-key">Branch</div><div class="meta-val" style="font-family:'JetBrains Mono',monospace;font-size:12px">{run.get('pr_branch','—')}</div></div>
    <div class="meta-cell"><div class="meta-key">Tech Stack</div><div class="meta-val">{run.get('tech_stack','—')}</div></div>
    <div class="meta-cell"><div class="meta-key">Verdict</div><div class="meta-val" style="color:{color}">{label}</div></div>
    <div class="meta-cell"><div class="meta-key">Confidence</div><div class="meta-val">{conf}</div></div>
    <div class="meta-cell"><div class="meta-key">Status</div><div class="meta-val">{run.get('status','—')}</div></div>
    <div class="meta-cell"><div class="meta-key">Duration</div><div class="meta-val">{run.get('duration_seconds','—')}s</div></div>
    <div class="meta-cell"><div class="meta-key">Started</div><div class="meta-val" style="font-size:12px">{(run.get('started_at','')[:19]).replace('T',' ')}</div></div>
    <div class="meta-cell"><div class="meta-key">Comment Posted</div><div class="meta-val">{'Yes' if run.get('comment_posted') else 'No'}</div></div>
  </div>

  {error_block}

  <h2>Agent trace — {len(logs)} steps</h2>
  {steps_html if steps_html else '<p style="color:#334155;padding:20px 0">No agent steps recorded.</p>'}
</body>
</html>"""
    return html