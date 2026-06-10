"""
audit_logger.py

SQLite audit logging for PR-Pilot reviews.
Every review run and every agent step is persisted so you can:
- See the full history of reviews
- Trace why a specific verdict was reached
- Debug failed or suspicious reviews

Tables:
  runs        — one row per PR review (metadata + final verdict)
  agent_logs  — one row per agent task output (full trace per run)
"""

import json
import sqlite3
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("PRPILOT_DB_PATH", "prpilot_audit.db")

# Thread-local storage for connections — SQLite connections are not
# thread-safe so each thread gets its own connection
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row   # rows behave like dicts
        _local.conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    return _local.conn


def init_db() -> None:
    """
    Create tables if they don't exist.
    Call once at application startup from api.py.
    """
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT    NOT NULL UNIQUE,   -- CrewAI crew execution ID
            repo_name       TEXT    NOT NULL,
            pr_number       INTEGER NOT NULL,
            pr_branch       TEXT,
            tech_stack      TEXT,
            verdict         TEXT,
            confidence      REAL,
            quality_score   REAL,
            security_score  REAL,
            comment_posted  INTEGER DEFAULT 0,         -- 1 = yes, 0 = no
            status          TEXT    NOT NULL DEFAULT 'started',  -- started|completed|failed
            error_message   TEXT,
            started_at      TEXT    NOT NULL,
            completed_at    TEXT,
            duration_seconds REAL
        );

        CREATE TABLE IF NOT EXISTS agent_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT    NOT NULL,              -- FK to runs.run_id
            agent_name  TEXT    NOT NULL,
            task_name   TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'completed',  -- completed|failed
            output      TEXT,                          -- full agent output (JSON or text)
            error       TEXT,
            duration_seconds REAL,
            logged_at   TEXT    NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE INDEX IF NOT EXISTS idx_runs_repo     ON runs(repo_name);
        CREATE INDEX IF NOT EXISTS idx_runs_status   ON runs(status);
        CREATE INDEX IF NOT EXISTS idx_logs_run_id   ON agent_logs(run_id);
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

def log_run_started(
    run_id: str,
    repo_name: str,
    pr_number: int,
    pr_branch: str = "",
    tech_stack: str = "",
) -> None:
    """Call when a crew execution starts."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO runs
            (run_id, repo_name, pr_number, pr_branch, tech_stack, status, started_at)
        VALUES (?, ?, ?, ?, ?, 'started', ?)
        """,
        (run_id, repo_name, pr_number, pr_branch, tech_stack,
         datetime.utcnow().isoformat()),
    )
    conn.commit()


def log_run_completed(
    run_id: str,
    verdict: str,
    confidence: float,
    quality_score: float,
    security_score: float,
    comment_posted: bool,
    duration_seconds: float,
) -> None:
    """Call when a crew execution finishes successfully."""
    conn = _get_conn()
    conn.execute(
        """
        UPDATE runs SET
            verdict          = ?,
            confidence       = ?,
            quality_score    = ?,
            security_score   = ?,
            comment_posted   = ?,
            status           = 'completed',
            completed_at     = ?,
            duration_seconds = ?
        WHERE run_id = ?
        """,
        (verdict, confidence, quality_score, security_score,
         1 if comment_posted else 0,
         datetime.utcnow().isoformat(),
         duration_seconds,
         run_id),
    )
    conn.commit()


def log_run_failed(run_id: str, error_message: str, duration_seconds: float) -> None:
    """Call when a crew execution fails."""
    conn = _get_conn()
    conn.execute(
        """
        UPDATE runs SET
            status           = 'failed',
            error_message    = ?,
            completed_at     = ?,
            duration_seconds = ?
        WHERE run_id = ?
        """,
        (error_message[:1000], datetime.utcnow().isoformat(), duration_seconds, run_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Agent step logging
# ---------------------------------------------------------------------------

def log_agent_step(
    run_id: str,
    agent_name: str,
    task_name: str,
    output: object,
    status: str = "completed",
    error: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Log one agent's output for a given run.
    output can be a dict, Pydantic model, or string — we serialise it.
    """
    if hasattr(output, "model_dump"):
        output_str = json.dumps(output.model_dump(), indent=2, default=str)
    elif isinstance(output, dict):
        output_str = json.dumps(output, indent=2, default=str)
    else:
        output_str = str(output)[:5000]   # hard cap — don't bloat the DB

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO agent_logs
            (run_id, agent_name, task_name, status, output, error, duration_seconds, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, agent_name, task_name, status,
         output_str, error, duration_seconds,
         datetime.utcnow().isoformat()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Query helpers (used by dashboard routes)
# ---------------------------------------------------------------------------

def get_recent_runs(limit: int = 20) -> list[dict]:
    """Return the most recent N runs, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT * FROM runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_run_by_id(run_id: str) -> Optional[dict]:
    """Return a single run by its CrewAI run_id."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row else None


def get_agent_logs_for_run(run_id: str) -> list[dict]:
    """Return all agent steps for a given run, in logged order."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT * FROM agent_logs
        WHERE run_id = ?
        ORDER BY id ASC
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Aggregate stats for the dashboard summary card."""
    conn = _get_conn()
    total     = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM runs WHERE status='completed'").fetchone()[0]
    failed    = conn.execute("SELECT COUNT(*) FROM runs WHERE status='failed'").fetchone()[0]
    avg_conf  = conn.execute(
        "SELECT AVG(confidence) FROM runs WHERE status='completed'"
    ).fetchone()[0]
    verdicts  = conn.execute(
        """
        SELECT verdict, COUNT(*) as count
        FROM runs WHERE status='completed'
        GROUP BY verdict
        ORDER BY count DESC
        """
    ).fetchall()

    return {
        "total_reviews":     total,
        "completed":         completed,
        "failed":            failed,
        "avg_confidence":    round(avg_conf * 100, 1) if avg_conf else 0,
        "verdict_breakdown": {r["verdict"]: r["count"] for r in verdicts},
    }