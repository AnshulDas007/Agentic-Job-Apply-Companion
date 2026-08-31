"""
SQLite database module for audit trail, job tracking, and usage logging.

Tables:
  - jobs: Scraped job listings with status tracking
  - applications: Individual application records
  - audit_trail: Timestamped action log for traceability
  - usage_log: LLM and Apify usage tracking for cost visibility
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/jobapply.db")


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    company_url TEXT NOT NULL DEFAULT '',
    legitimacy_score REAL,
    relevance_score REAL,
    status TEXT NOT NULL DEFAULT 'scraped',
    scraped_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    cover_letter_path TEXT,
    legal_review_summary TEXT,
    submitted_at TEXT,
    reviewed_by TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    service TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_estimate REAL NOT NULL DEFAULT 0.0,
    latency_ms REAL NOT NULL DEFAULT 0.0
);
"""


# ---------------------------------------------------------------------------
# Database wrapper
# ---------------------------------------------------------------------------

class Database:
    """
    SQLite database wrapper for job application tracking and audit logging.

    Usage:
        db = Database()  # auto-creates tables on first run
        db.insert_job({...})
        db.log_audit("scrape", "linkedin", "Scraped 50 jobs")
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create the SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent read performance
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # -------------------------------------------------------------------
    # Jobs
    # -------------------------------------------------------------------

    def insert_job(self, job: Dict[str, Any]) -> str:
        """
        Insert a job listing into the database.

        Args:
            job: Dict with keys matching the jobs table columns.
                 Must include: id, title, company, url.

        Returns:
            The job ID.
        """
        conn = self._get_connection()
        now = _now_iso()

        conn.execute(
            """INSERT OR REPLACE INTO jobs
               (id, title, company, url, source, description, location,
                company_url, legitimacy_score, relevance_score, status, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job["id"],
                job["title"],
                job["company"],
                job["url"],
                job.get("source", ""),
                job.get("description", ""),
                job.get("location", ""),
                job.get("company_url", ""),
                job.get("legitimacy_score"),
                job.get("relevance_score"),
                job.get("status", "scraped"),
                job.get("scraped_at", now),
            ),
        )
        conn.commit()
        return job["id"]

    def update_job_status(
        self, job_id: str, status: str, **kwargs: Any
    ) -> None:
        """Update a job's status and optional fields."""
        conn = self._get_connection()
        set_clauses = ["status = ?"]
        values: list[Any] = [status]

        for col in ("legitimacy_score", "relevance_score", "processed_at"):
            if col in kwargs:
                set_clauses.append(f"{col} = ?")
                values.append(kwargs[col])

        values.append(job_id)
        conn.execute(
            f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        conn.commit()

    def get_jobs(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieve jobs, optionally filtered by status."""
        conn = self._get_connection()
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY scraped_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single job by ID."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    # -------------------------------------------------------------------
    # Applications
    # -------------------------------------------------------------------

    def insert_application(self, app: Dict[str, Any]) -> str:
        """Insert an application record."""
        conn = self._get_connection()
        now = _now_iso()

        conn.execute(
            """INSERT OR REPLACE INTO applications
               (id, job_id, tier, status, cover_letter_path,
                legal_review_summary, submitted_at, reviewed_by, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                app["id"],
                app["job_id"],
                app.get("tier", ""),
                app.get("status", "pending"),
                app.get("cover_letter_path"),
                app.get("legal_review_summary"),
                app.get("submitted_at"),
                app.get("reviewed_by"),
                app.get("notes", ""),
                app.get("created_at", now),
            ),
        )
        conn.commit()
        return app["id"]

    def update_application_status(
        self, app_id: str, status: str, **kwargs: Any
    ) -> None:
        """Update an application's status."""
        conn = self._get_connection()
        set_clauses = ["status = ?"]
        values: list[Any] = [status]

        for col in ("submitted_at", "reviewed_by", "notes"):
            if col in kwargs:
                set_clauses.append(f"{col} = ?")
                values.append(kwargs[col])

        values.append(app_id)
        conn.execute(
            f"UPDATE applications SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        conn.commit()

    def get_applications(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieve applications, optionally filtered by status."""
        conn = self._get_connection()
        if status:
            rows = conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # Audit Trail
    # -------------------------------------------------------------------

    def log_audit(
        self,
        action: str,
        target: str = "",
        details: str = "",
        result: str = "",
    ) -> int:
        """
        Log an action to the audit trail.

        Args:
            action: What happened (e.g., "scrape", "apply", "legal_review").
            target: What it happened to (e.g., job URL, company name).
            details: Additional context.
            result: Outcome (e.g., "success", "blocked", "rejected").

        Returns:
            The audit trail entry ID.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """INSERT INTO audit_trail (timestamp, action, target, details, result)
               VALUES (?, ?, ?, ?, ?)""",
            (_now_iso(), action, target, details, result),
        )
        conn.commit()
        return cursor.lastrowid

    def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent audit trail entries."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # Usage Log
    # -------------------------------------------------------------------

    def log_usage(
        self,
        service: str,
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_estimate: float = 0.0,
        latency_ms: float = 0.0,
    ) -> int:
        """
        Log an LLM or API usage entry.

        Args:
            service: Provider name (e.g., "groq", "apify").
            model: Model name.
            tokens_in: Input tokens.
            tokens_out: Output tokens.
            cost_estimate: Estimated cost in USD.
            latency_ms: Call latency in milliseconds.

        Returns:
            The usage log entry ID.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """INSERT INTO usage_log
               (timestamp, service, model, tokens_in, tokens_out,
                cost_estimate, latency_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_now_iso(), service, model, tokens_in, tokens_out,
             cost_estimate, latency_ms),
        )
        conn.commit()
        return cursor.lastrowid

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get aggregated usage statistics."""
        conn = self._get_connection()

        row = conn.execute(
            """SELECT
                 COUNT(*) as total_calls,
                 SUM(tokens_in) as total_tokens_in,
                 SUM(tokens_out) as total_tokens_out,
                 SUM(cost_estimate) as total_cost,
                 AVG(latency_ms) as avg_latency_ms
               FROM usage_log"""
        ).fetchone()

        return dict(row) if row else {}

    def get_usage_by_service(self) -> List[Dict[str, Any]]:
        """Get usage statistics grouped by service."""
        conn = self._get_connection()
        rows = conn.execute(
            """SELECT
                 service,
                 COUNT(*) as call_count,
                 SUM(tokens_in) as total_tokens_in,
                 SUM(tokens_out) as total_tokens_out,
                 SUM(cost_estimate) as total_cost
               FROM usage_log
               GROUP BY service
               ORDER BY call_count DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get overall pipeline statistics for the status dashboard."""
        conn = self._get_connection()

        job_counts = conn.execute(
            """SELECT status, COUNT(*) as count
               FROM jobs GROUP BY status"""
        ).fetchall()

        app_counts = conn.execute(
            """SELECT status, COUNT(*) as count
               FROM applications GROUP BY status"""
        ).fetchall()

        return {
            "jobs": {row["status"]: row["count"] for row in job_counts},
            "applications": {row["status"]: row["count"] for row in app_counts},
            "usage": self.get_usage_summary(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()
