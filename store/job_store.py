import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_PKT = ZoneInfo("Asia/Karachi")

from scrapers.base import Job
from ai.models import ScoringResult

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    posted_at TEXT,
    semantic_score REAL,
    llm_score INTEGER,
    matching_skills TEXT,
    missing_skills TEXT,
    reason TEXT,
    seniority_match INTEGER,
    seniority_level TEXT,
    location_ok INTEGER,
    salary_ok INTEGER,
    requires_visa INTEGER,
    notified INTEGER DEFAULT 0,
    notified_at TEXT,
    seen_at TEXT NOT NULL
);
"""

# Columns added after initial schema — migrated at startup if missing.
_MIGRATIONS = [
    ("seniority_level", "TEXT"),
    ("location_ok", "INTEGER"),
    ("salary_ok", "INTEGER"),
    ("requires_visa", "INTEGER"),
    ("posted_at", "TEXT"),
    ("notified_at", "TEXT"),
]


class JobStore:
    def __init__(self, data_dir: str):
        self.db_path = Path(data_dir) / "jobs.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA)
            for col, typedef in _MIGRATIONS:
                try:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typedef}")
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_seen_at ON jobs (seen_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs (notified)")

    def is_seen(self, job_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return row is not None

    def seen_ids(self, job_ids: list[str]) -> set[str]:
        if not job_ids:
            return set()
        placeholders = ",".join("?" * len(job_ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM jobs WHERE id IN ({placeholders})", job_ids
            ).fetchall()
        return {row["id"] for row in rows}

    def save_filtered(self, job: Job, semantic_score: float) -> None:
        self._upsert(job, semantic_score=semantic_score)

    def save_scored(self, job: Job, semantic_score: float, result: ScoringResult, notified: bool) -> None:
        self._upsert(
            job,
            semantic_score=semantic_score,
            llm_score=result.score,
            matching_skills=result.matching_skills,
            missing_skills=result.missing_skills,
            reason=result.reason,
            seniority_match=result.seniority_match,
            seniority_level=result.seniority_level,
            location_ok=result.location_ok,
            salary_ok=result.salary_ok,
            requires_visa=result.requires_visa,
            notified=notified,
        )

    def _upsert(
        self,
        job: Job,
        semantic_score: float = 0.0,
        llm_score: int = None,
        matching_skills: list[str] = None,
        missing_skills: list[str] = None,
        reason: str = None,
        seniority_match: bool = None,
        seniority_level: str = None,
        location_ok: bool = None,
        salary_ok: bool = None,
        requires_visa: bool = None,
        notified: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (id, title, company, url, source, posted_at, semantic_score, llm_score,
                    matching_skills, missing_skills, reason, seniority_match,
                    seniority_level, location_ok, salary_ok, requires_visa,
                    notified, seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.id,
                    job.title,
                    job.company,
                    job.url,
                    job.source,
                    job.posted_at or None,
                    semantic_score,
                    llm_score,
                    json.dumps(matching_skills or []),
                    json.dumps(missing_skills or []),
                    reason,
                    int(seniority_match) if seniority_match is not None else None,
                    seniority_level,
                    int(location_ok) if location_ok is not None else None,
                    int(salary_ok) if salary_ok is not None else None,
                    int(requires_visa) if requires_visa is not None else None,
                    int(notified),
                    datetime.now(_PKT).isoformat(),
                ),
            )

    def notified_today(self) -> int:
        today = datetime.now(_PKT).date().isoformat()
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE notified = 1 AND notified_at LIKE ?",
                (f"{today}%",),
            ).fetchone()[0]

    def mark_notified(self, job_ids: list[str]) -> None:
        now = datetime.now(_PKT).isoformat()
        with self._connect() as conn:
            conn.executemany(
                "UPDATE jobs SET notified = 1, notified_at = ? WHERE id = ?",
                [(now, jid) for jid in job_ids],
            )

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            notified = conn.execute("SELECT COUNT(*) FROM jobs WHERE notified = 1").fetchone()[0]
            return {"total_seen": total, "total_notified": notified}
