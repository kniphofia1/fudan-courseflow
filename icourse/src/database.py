"""SQLite storage for tracking courses and lectures."""

import os
import sqlite3
from datetime import datetime

from . import config


class Database:
    """SQLite database for course and lecture tracking."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS courses (
                    course_id TEXT PRIMARY KEY,
                    title TEXT,
                    teacher TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS lectures (
                    sub_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    sub_title TEXT,
                    date TEXT,
                    transcript TEXT,
                    summary TEXT,
                    processed_at TEXT,
                    emailed_at TEXT,
                    FOREIGN KEY (course_id) REFERENCES courses(course_id)
                )
            """)
            # Migrate: add error tracking and summary_model columns
            existing = {
                row[1]
                for row in self.conn.execute("PRAGMA table_info(lectures)").fetchall()
            }
            for col, typedef in [
                ("error_msg", "TEXT"),
                ("error_count", "INTEGER DEFAULT 0"),
                ("error_stage", "TEXT"),
                ("summary_model", "TEXT"),
                ("exported_at", "TEXT"),
                ("export_path", "TEXT"),
            ]:
                if col not in existing:
                    self.conn.execute(f"ALTER TABLE lectures ADD COLUMN {col} {typedef}")

    def upsert_course(self, course_id: str, title: str, teacher: str):
        with self.conn:
            self.conn.execute(
                """INSERT INTO courses (course_id, title, teacher)
                   VALUES (?, ?, ?)
                   ON CONFLICT(course_id) DO UPDATE SET
                       title=excluded.title, teacher=excluded.teacher""",
                (course_id, title, teacher),
            )

    def insert_lecture(
        self, sub_id: str, course_id: str, sub_title: str, date: str
    ) -> bool:
        """Insert a new lecture. Returns True if inserted, False if already exists."""
        try:
            with self.conn:
                self.conn.execute(
                    """INSERT INTO lectures (sub_id, course_id, sub_title, date)
                       VALUES (?, ?, ?, ?)""",
                    (sub_id, course_id, sub_title, date),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_processed_sub_ids(self, course_id: str) -> set[str]:
        """Return sub_ids that have been fully processed."""
        rows = self.conn.execute(
            "SELECT sub_id FROM lectures WHERE course_id = ? AND processed_at IS NOT NULL",
            (course_id,),
        ).fetchall()
        return {row["sub_id"] for row in rows}

    def get_unprocessed_lectures(self, course_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM lectures WHERE processed_at IS NULL"
        params = ()
        if course_id:
            query += " AND course_id = ?"
            params = (course_id,)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_transcript(self, sub_id: str, transcript: str):
        with self.conn:
            self.conn.execute(
                "UPDATE lectures SET transcript = ? WHERE sub_id = ?",
                (transcript, sub_id),
            )

    def update_summary(self, sub_id: str, summary: str):
        with self.conn:
            self.conn.execute(
                "UPDATE lectures SET summary = ? WHERE sub_id = ?",
                (summary, sub_id),
            )

    def mark_processed(self, sub_id: str):
        with self.conn:
            self.conn.execute(
                "UPDATE lectures SET processed_at = ? WHERE sub_id = ?",
                (datetime.now().isoformat(), sub_id),
            )

    def mark_emailed(self, sub_id: str):
        with self.conn:
            self.conn.execute(
                "UPDATE lectures SET emailed_at = ? WHERE sub_id = ?",
                (datetime.now().isoformat(), sub_id),
            )

    def mark_emailed_batch(self, sub_ids: list[str]):
        """Mark multiple lectures as emailed in a single transaction."""
        if not sub_ids:
            return
        now = datetime.now().isoformat()
        with self.conn:
            self.conn.executemany(
                "UPDATE lectures SET emailed_at = ? WHERE sub_id = ?",
                [(now, sid) for sid in sub_ids],
            )

    def update_error(self, sub_id: str, stage: str, error_msg: str):
        """Record a processing error for a lecture."""
        with self.conn:
            self.conn.execute(
                """UPDATE lectures
                   SET error_stage = ?, error_msg = ?,
                       error_count = COALESCE(error_count, 0) + 1
                   WHERE sub_id = ?""",
                (stage, error_msg, sub_id),
            )

    def clear_error(self, sub_id: str):
        """Clear error state after successful processing."""
        with self.conn:
            self.conn.execute(
                """UPDATE lectures
                   SET error_stage = NULL, error_msg = NULL, error_count = 0
                   WHERE sub_id = ?""",
                (sub_id,),
            )

    def update_summary_with_model(self, sub_id: str, summary: str, model: str):
        """Save summary and the model that produced it."""
        with self.conn:
            self.conn.execute(
                "UPDATE lectures SET summary = ?, summary_model = ? WHERE sub_id = ?",
                (summary, model, sub_id),
            )

    def get_lecture(self, sub_id: str) -> dict | None:
        """Get a single lecture row by sub_id."""
        row = self.conn.execute(
            "SELECT * FROM lectures WHERE sub_id = ?", (sub_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_unsent_lectures(self) -> list[dict]:
        """Find lectures that are processed but not yet emailed."""
        rows = self.conn.execute(
            """SELECT l.*, c.title AS course_title, c.teacher
               FROM lectures l
               JOIN courses c ON l.course_id = c.course_id
               WHERE l.processed_at IS NOT NULL
                 AND l.emailed_at IS NULL
                 AND l.summary IS NOT NULL""",
        ).fetchall()
        return [dict(row) for row in rows]

    def get_unexported_summaries(self) -> list[dict]:
        """Return processed summaries that have not been written to Markdown."""

        rows = self.conn.execute(
            """SELECT l.*, c.title AS course_title, c.teacher
               FROM lectures l
               JOIN courses c ON l.course_id = c.course_id
               WHERE l.processed_at IS NOT NULL
                 AND l.summary IS NOT NULL
                 AND l.exported_at IS NULL
               ORDER BY c.course_id, l.date, l.sub_id"""
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_exported(self, sub_id: str, export_path: str):
        """Record the successful Markdown destination for one lecture."""

        with self.conn:
            self.conn.execute(
                """UPDATE lectures
                   SET exported_at = ?, export_path = ?
                   WHERE sub_id = ?""",
                (datetime.now().isoformat(), export_path, sub_id),
            )
