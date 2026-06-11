"""
dashboard.py

Simple read-only dashboard for PR-Pilot audit logs.
Mount this in api.py with: app.include_router(dashboard_router)

Routes:
  GET /runs            — list recent reviews (JSON + HTML)
  GET /runs/{run_id}   — full trace for one review
  GET /stats           — summary stats
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from prtool.audit_logger import get_recent_runs, get_run_by_id, get_agent_logs_for_run, get_stats

dashboard_router = APIRouter(prefix="/dashboard")


# ---------------------------------------------------------------------------
# JSON API routes (used programmatically)
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

@dashboard_router.get("/", response_class=HTMLResponse)
def dashboard_html():
    runs = get_recent_runs(50)
    stats = get_stats()

    verdict_colors = {
        "strongly_recommend_merge": "#22c55e",
        "merge":                    "#22c55e",
        "merge_with_suggestions":   "#f59e0b",
        "merge_with_advice":        "#f59e0b",
        "needs_work":               "#f97316",
        "needs_human_review":       "#f97316",
        "do_not_merge":             "#ef4444",
        "block":                    "#ef4444",
        "unknown":                  "#6b7280",
        "failed":                   "#ef4444",
    }

    status_colors = {
        "completed": "#22c55e",
        "started":   "#f59e0b",
        "failed":    "#ef4444",
    }

    def verdict_badge(verdict):
        color = verdict_colors.get(verdict, "#6b7280")
        label = (verdict or "unknown").replace("_", " ").title()
        return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px">{label}</span>'

    def status_badge(status):
        color = status_colors.get(status, "#6b7280")
        return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px">{status}</span>'

    rows = ""
    for r in runs:
        conf = f"{round(r['confidence'] * 100)}%" if r.get("confidence") else "—"
        dur  = f"{r['duration_seconds']}s" if r.get("duration_seconds") else "—"
        rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #1f2937">
                <a href="/dashboard/runs/{r['run_id']}" style="color:#60a5fa;text-decoration:none">
                    {r['run_id'][:8]}...
                </a>
            </td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{r['repo_name']}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">#{r['pr_number']}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{r.get('tech_stack','—')}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{verdict_badge(r.get('verdict','unknown'))}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{conf}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{status_badge(r.get('status','unknown'))}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{dur}</td>
            <td style="padding:8px;border-bottom:1px solid #1f2937">{r.get('started_at','')[:16]}</td>
        </tr>"""

    verdict_breakdown = ""
    for v, count in stats.get("verdict_breakdown", {}).items():
        color = verdict_colors.get(v, "#6b7280")
        label = v.replace("_", " ").title()
        verdict_breakdown += f'<div style="margin:4px 0"><span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px">{label}</span> <strong style="color:#e5e7eb">{count}</strong></div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>PR-Pilot Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #0f172a; color: #e5e7eb; margin: 0; padding: 24px; }}
        h1 {{ color: #f1f5f9; margin-bottom: 4px; }}
        h2 {{ color: #94a3b8; font-size: 14px; font-weight: normal; margin-top: 0; }}
        .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 24px 0; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 20px; min-width: 160px; }}
        .card-value {{ font-size: 32px; font-weight: bold; color: #f1f5f9; }}
        .card-label {{ color: #64748b; font-size: 13px; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b;
                 border-radius: 8px; overflow: hidden; }}
        th {{ background: #0f172a; padding: 10px 8px; text-align: left;
              color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
        tr:hover td {{ background: #263148; }}
        a {{ color: #60a5fa; }}
    </style>
</head>
<body>
    <h1>PR-Pilot Dashboard</h1>
    <h2>Audit log of all PR reviews</h2>

    <div class="cards">
        <div class="card">
            <div class="card-value">{stats.get('total_reviews', 0)}</div>
            <div class="card-label">Total Reviews</div>
        </div>
        <div class="card">
            <div class="card-value" style="color:#22c55e">{stats.get('completed', 0)}</div>
            <div class="card-label">Completed</div>
        </div>
        <div class="card">
            <div class="card-value" style="color:#ef4444">{stats.get('failed', 0)}</div>
            <div class="card-label">Failed</div>
        </div>
        <div class="card">
            <div class="card-value">{stats.get('avg_confidence', 0)}%</div>
            <div class="card-label">Avg Confidence</div>
        </div>
        <div class="card">
            <div class="card-label" style="margin-bottom:8px">Verdict Breakdown</div>
            {verdict_breakdown or '<span style="color:#64748b">No data yet</span>'}
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Run ID</th>
                <th>Repo</th>
                <th>PR</th>
                <th>Tech Stack</th>
                <th>Verdict</th>
                <th>Confidence</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Started</th>
            </tr>
        </thead>
        <tbody>
            {rows if rows else '<tr><td colspan="9" style="padding:24px;text-align:center;color:#64748b">No reviews logged yet. Open a PR to get started.</td></tr>'}
        </tbody>
    </table>
</body>
</html>"""
    return html


@dashboard_router.get("/runs/{run_id}/html", response_class=HTMLResponse)
def run_detail_html(run_id: str):
    run = get_run_by_id(run_id)
    if not run:
        return HTMLResponse("<h1>Run not found</h1>", status_code=404)

    logs = get_agent_logs_for_run(run_id)

    steps_html = ""
    for log in logs:
        output_preview = (log.get("output") or "")[:2000]
        steps_html += f"""
        <div style="background:#1e293b;border-radius:8px;padding:16px;margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                <strong style="color:#f1f5f9">{log['agent_name']}</strong>
                <span style="color:#64748b;font-size:12px">{log['task_name']}</span>
            </div>
            <pre style="background:#0f172a;padding:12px;border-radius:4px;font-size:12px;
                        overflow-x:auto;white-space:pre-wrap;color:#94a3b8">{output_preview}</pre>
        </div>"""

    conf = f"{round(run['confidence'] * 100)}%" if run.get("confidence") else "—"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Run {run_id[:8]} — PR-Pilot</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #0f172a; color: #e5e7eb; margin: 0; padding: 24px; }}
        h1 {{ color: #f1f5f9; }}
        .meta {{ background: #1e293b; border-radius: 8px; padding: 16px; margin: 16px 0;
                 display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .meta-item span:first-child {{ color: #64748b; font-size: 12px; display: block; }}
        a {{ color: #60a5fa; }}
    </style>
</head>
<body>
    <a href="/dashboard/" style="color:#64748b;text-decoration:none">← Back to dashboard</a>
    <h1>Run {run_id[:8]}...</h1>

    <div class="meta">
        <div class="meta-item"><span>Repo</span><strong>{run['repo_name']}</strong></div>
        <div class="meta-item"><span>PR</span><strong>#{run['pr_number']}</strong></div>
        <div class="meta-item"><span>Branch</span><strong>{run.get('pr_branch','—')}</strong></div>
        <div class="meta-item"><span>Tech Stack</span><strong>{run.get('tech_stack','—')}</strong></div>
        <div class="meta-item"><span>Verdict</span><strong>{run.get('verdict','—')}</strong></div>
        <div class="meta-item"><span>Confidence</span><strong>{conf}</strong></div>
        <div class="meta-item"><span>Status</span><strong>{run.get('status','—')}</strong></div>
        <div class="meta-item"><span>Duration</span><strong>{run.get('duration_seconds','—')}s</strong></div>
        <div class="meta-item"><span>Started</span><strong>{run.get('started_at','')[:19]}</strong></div>
        <div class="meta-item"><span>Comment Posted</span><strong>{'Yes' if run.get('comment_posted') else 'No'}</strong></div>
    </div>

    {"<div style='background:#7f1d1d;border-radius:8px;padding:12px;margin:12px 0'><strong>Error:</strong> " + run['error_message'] + "</div>" if run.get('error_message') else ""}

    <h2 style="color:#94a3b8">Agent Trace ({len(logs)} steps)</h2>
    {steps_html if steps_html else '<p style="color:#64748b">No agent steps logged.</p>'}
</body>
</html>"""
    return html