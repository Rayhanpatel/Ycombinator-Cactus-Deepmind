"""
SQLite persistence layer for HVAC field-tech findings, safety flags, and scope changes.

Usage:
    from src.db import HVACDatabase
    db = HVACDatabase("data/findings.db")
    db.init_db()
    row_id = db.insert_finding(job_id="JOB-001", location="outdoor condenser", ...)
"""

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class HVACDatabase:
    """SQLite-backed storage for job findings, safety flags, and scope changes."""

    def __init__(self, db_path: str = "data/findings.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None

    def init_db(self) -> None:
        """Create tables if they don't exist."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                closed_at   TEXT,
                summary     TEXT,
                status      TEXT NOT NULL DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS findings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id      TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                location    TEXT NOT NULL,
                issue       TEXT NOT NULL,
                severity    TEXT NOT NULL CHECK(severity IN ('info','minor','major','critical')),
                part_number TEXT,
                notes       TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS safety_flags (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id           TEXT NOT NULL,
                timestamp        TEXT NOT NULL,
                hazard           TEXT NOT NULL,
                immediate_action TEXT NOT NULL,
                level            TEXT NOT NULL CHECK(level IN ('caution','stop')),
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS scope_changes (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id                      TEXT NOT NULL,
                timestamp                   TEXT NOT NULL,
                original_scope              TEXT NOT NULL,
                new_scope                   TEXT NOT NULL,
                reason                      TEXT NOT NULL,
                estimated_extra_time_minutes INTEGER,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );
        """)
        self.conn.commit()
        logger.info(f"✅ Database initialized at {self.db_path}")

    def _ensure_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            self.init_db()
        return self.conn  # type: ignore

    # ── Job Management ────────────────────────────────────────

    def create_job(self, job_id: Optional[str] = None) -> str:
        """Create a new job. Returns the job ID."""
        conn = self._ensure_conn()
        if job_id is None:
            # Auto-generate
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            count = cursor.fetchone()[0]
            job_id = f"JOB-{count + 1:04d}"

        now = datetime.now().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO jobs (id, created_at, status) VALUES (?, ?, 'open')",
            (job_id, now),
        )
        conn.commit()
        logger.info(f"📋 Created job: {job_id}")
        return job_id

    def close_job(self, job_id: str, summary: str) -> None:
        """Mark a job as closed."""
        conn = self._ensure_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE jobs SET status='closed', closed_at=?, summary=? WHERE id=?",
            (now, summary, job_id),
        )
        conn.commit()

    # ── Findings ──────────────────────────────────────────────

    def insert_finding(
        self,
        job_id: str,
        location: str,
        issue: str,
        severity: str,
        part_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Insert a finding and return the row ID."""
        conn = self._ensure_conn()
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """INSERT INTO findings (job_id, timestamp, location, issue, severity, part_number, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, now, location, issue, severity, part_number, notes),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.info(f"📝 Logged finding #{row_id}: [{severity}] {issue}")
        return row_id  # type: ignore

    def get_findings_for_job(self, job_id: str) -> list[dict]:
        """Return all findings for a given job."""
        conn = self._ensure_conn()
        cursor = conn.execute(
            "SELECT * FROM findings WHERE job_id = ? ORDER BY timestamp",
            (job_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ── Safety Flags ──────────────────────────────────────────

    def insert_safety_flag(
        self,
        job_id: str,
        hazard: str,
        immediate_action: str,
        level: str,
    ) -> int:
        """Insert a safety flag and return the row ID."""
        conn = self._ensure_conn()
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """INSERT INTO safety_flags (job_id, timestamp, hazard, immediate_action, level)
               VALUES (?, ?, ?, ?, ?)""",
            (job_id, now, hazard, immediate_action, level),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.info(f"🚨 Safety flag #{row_id}: [{level}] {hazard}")
        return row_id  # type: ignore

    def get_safety_flags_for_job(self, job_id: str) -> list[dict]:
        """Return all safety flags for a given job."""
        conn = self._ensure_conn()
        cursor = conn.execute(
            "SELECT * FROM safety_flags WHERE job_id = ? ORDER BY timestamp",
            (job_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ── Scope Changes ─────────────────────────────────────────

    def insert_scope_change(
        self,
        job_id: str,
        original_scope: str,
        new_scope: str,
        reason: str,
        estimated_extra_time_minutes: Optional[int] = None,
    ) -> int:
        """Insert a scope change and return the row ID."""
        conn = self._ensure_conn()
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """INSERT INTO scope_changes
               (job_id, timestamp, original_scope, new_scope, reason, estimated_extra_time_minutes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_id, now, original_scope, new_scope, reason, estimated_extra_time_minutes),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.info(f"🔄 Scope change #{row_id}: {original_scope} → {new_scope}")
        return row_id  # type: ignore

    def get_scope_changes_for_job(self, job_id: str) -> list[dict]:
        """Return all scope changes for a given job."""
        conn = self._ensure_conn()
        cursor = conn.execute(
            "SELECT * FROM scope_changes WHERE job_id = ? ORDER BY timestamp",
            (job_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ── Full Job Export ───────────────────────────────────────

    def export_job(self, job_id: str) -> dict:
        """Export a complete job record as a dictionary."""
        conn = self._ensure_conn()

        # Job metadata
        cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        job_row = cursor.fetchone()
        if job_row is None:
            return {"error": f"Job {job_id} not found"}

        return {
            "job": dict(job_row),
            "findings": self.get_findings_for_job(job_id),
            "safety_flags": self.get_safety_flags_for_job(job_id),
            "scope_changes": self.get_scope_changes_for_job(job_id),
            "exported_at": datetime.now().isoformat(),
        }

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
