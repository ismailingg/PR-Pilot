import sqlite3

conn = sqlite3.connect('prpilot_audit.db')
conn.row_factory = sqlite3.Row

print("=" * 60)
print("RUNS TABLE")
print("=" * 60)
runs = conn.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 5').fetchall()
print(f"Total runs logged: {len(runs)}")
for r in runs:
    print(f"\n  run_id:    {r['run_id'][:8]}...")
    print(f"  repo:      {r['repo_name']}")
    print(f"  PR:        #{r['pr_number']}")
    print(f"  branch:    {r['pr_branch']}")
    print(f"  tech:      {r['tech_stack']}")
    print(f"  verdict:   {r['verdict']}")
    print(f"  status:    {r['status']}")
    print(f"  duration:  {r['duration_seconds']}s")
    print(f"  posted:    {bool(r['comment_posted'])}")
    if r['error_message']:
        print(f"  error:     {r['error_message'][:100]}")

print("\n" + "=" * 60)
print("AGENT LOGS TABLE")
print("=" * 60)
total_logs = conn.execute('SELECT COUNT(*) FROM agent_logs').fetchone()[0]
print(f"Total agent steps logged: {total_logs}")

if runs:
    latest_run_id = runs[0]['run_id']
    steps = conn.execute(
        'SELECT agent_name, task_name, status FROM agent_logs WHERE run_id = ? ORDER BY id ASC',
        (latest_run_id,)
    ).fetchall()
    print(f"\nSteps for latest run ({latest_run_id[:8]}...):")
    for s in steps:
        print(f"  {s['agent_name']:<30} | {s['task_name']:<25} | {s['status']}")

conn.close()