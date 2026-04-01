"""SQLite cache for triage data with WAL mode and thread-safe writes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.triage.models import (
    FollowUp,
    FollowUpStatus,
    ImportanceScore,
    MessageCategory,
    PrioritySender,
    ScoringSignal,
    SenderTier,
    SyncState,
)

_SCORE_TTL_HOURS = 24
_METADATA_TTL_DAYS = 30
_MAX_MESSAGE_CACHE_ROWS = 50_000

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS message_cache (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    account_hash TEXT NOT NULL,
    from_hash TEXT NOT NULL,
    to_hashes TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    date_received TEXT NOT NULL,
    label_ids TEXT NOT NULL,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    header_list_unsubscribe INTEGER NOT NULL DEFAULT 0,
    header_precedence_bulk INTEGER NOT NULL DEFAULT 0,
    priority_sender_tier TEXT,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS importance_scores (
    message_id TEXT PRIMARY KEY REFERENCES message_cache(message_id),
    score REAL NOT NULL,
    category TEXT NOT NULL,
    signals TEXT NOT NULL,
    scored_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    account_hash TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    sent_date TEXT NOT NULL,
    expected_reply_days INTEGER NOT NULL,
    deadline TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS priority_senders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_pattern TEXT UNIQUE NOT NULL,
    tier TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    account_hash TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    sync_token TEXT,
    last_sync TEXT NOT NULL,
    messages_cached INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cache_account ON message_cache(account_hash);
CREATE INDEX IF NOT EXISTS idx_cache_date ON message_cache(date_received);
CREATE INDEX IF NOT EXISTS idx_cache_thread ON message_cache(thread_id);
CREATE INDEX IF NOT EXISTS idx_followup_status ON follow_ups(status);
CREATE INDEX IF NOT EXISTS idx_followup_account ON follow_ups(account_hash);
CREATE INDEX IF NOT EXISTS idx_scores_scored_at ON importance_scores(scored_at);
"""


class TriageCache:
    """SQLite-backed cache for triage metadata, scores, and follow-ups."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create tables and enable WAL journal mode."""
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a write query under the write lock."""
        assert self._conn is not None
        with self._write_lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def _execute_read(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a read query and return rows as dicts."""
        assert self._conn is not None
        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    # -- Message metadata --

    def cache_message_metadata(self, msg_meta: dict[str, Any]) -> None:
        """Insert or update message metadata in the cache."""
        now = datetime.now(tz=UTC).isoformat()
        self._execute_write(
            """INSERT INTO message_cache
               (message_id, thread_id, account_hash, from_hash, to_hashes,
                subject_hash, date_received, label_ids, has_attachments,
                header_list_unsubscribe, header_precedence_bulk,
                priority_sender_tier, cached_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(message_id) DO UPDATE SET
                 label_ids = excluded.label_ids,
                 priority_sender_tier = excluded.priority_sender_tier,
                 cached_at = excluded.cached_at""",
            (
                msg_meta["message_id"],
                msg_meta["thread_id"],
                msg_meta["account_hash"],
                msg_meta["from_hash"],
                msg_meta["to_hashes"],
                msg_meta["subject_hash"],
                msg_meta["date_received"],
                msg_meta["label_ids"],
                int(msg_meta["has_attachments"]),
                int(msg_meta["header_list_unsubscribe"]),
                int(msg_meta["header_precedence_bulk"]),
                msg_meta["priority_sender_tier"],
                now,
            ),
        )
        self._enforce_max_rows()

    def get_cached_message(self, message_id: str) -> dict[str, Any] | None:
        """Retrieve a single cached message by ID."""
        rows = self._execute_read("SELECT * FROM message_cache WHERE message_id = ?", (message_id,))
        return rows[0] if rows else None

    def get_cached_messages(
        self, account_hash: str, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve cached messages for an account, optionally filtered by date."""
        if since is not None:
            return self._execute_read(
                "SELECT * FROM message_cache WHERE account_hash = ? AND date_received >= ?",
                (account_hash, since.isoformat()),
            )
        return self._execute_read(
            "SELECT * FROM message_cache WHERE account_hash = ?",
            (account_hash,),
        )

    # -- Importance scores --

    def store_score(self, score: ImportanceScore) -> None:
        """Store or update an importance score."""
        now = datetime.now(tz=UTC).isoformat()
        signals_json = json.dumps([s.model_dump() for s in score.signals])
        self._execute_write(
            """INSERT INTO importance_scores (message_id, score, category, signals, scored_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(message_id) DO UPDATE SET
                 score = excluded.score,
                 category = excluded.category,
                 signals = excluded.signals,
                 scored_at = excluded.scored_at""",
            (score.message_id, score.score, score.category.value, signals_json, now),
        )

    def get_score(self, message_id: str) -> ImportanceScore | None:
        """Retrieve an importance score by message ID."""
        rows = self._execute_read(
            "SELECT * FROM importance_scores WHERE message_id = ?", (message_id,)
        )
        if not rows:
            return None
        return self._row_to_score(rows[0])

    def get_valid_score(self, message_id: str) -> ImportanceScore | None:
        """Retrieve a score only if it was computed within the TTL window."""
        cutoff = (datetime.now(tz=UTC) - timedelta(hours=_SCORE_TTL_HOURS)).isoformat()
        rows = self._execute_read(
            "SELECT * FROM importance_scores WHERE message_id = ? AND scored_at > ?",
            (message_id, cutoff),
        )
        if not rows:
            return None
        return self._row_to_score(rows[0])

    # -- Follow-ups --

    def add_follow_up(self, follow_up: FollowUp, account_hash: str = "") -> int:
        """Add a follow-up tracker. Returns the row ID."""
        now = datetime.now(tz=UTC).isoformat()
        cursor = self._execute_write(
            """INSERT INTO follow_ups
               (message_id, thread_id, account_hash, subject_hash, sent_date,
                expected_reply_days, deadline, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                follow_up.message_id,
                follow_up.thread_id,
                account_hash,
                follow_up.subject_hash,
                follow_up.sent_date.isoformat(),
                follow_up.expected_reply_days,
                follow_up.deadline.isoformat() if follow_up.deadline else None,
                follow_up.status.value,
                now,
                now,
            ),
        )
        return cursor.lastrowid or 0

    def get_follow_ups(
        self, account_hash: str, status: FollowUpStatus | None = None
    ) -> list[FollowUp]:
        """Retrieve follow-ups for an account, optionally filtered by status."""
        if status is not None:
            rows = self._execute_read(
                "SELECT * FROM follow_ups WHERE account_hash = ? AND status = ?",
                (account_hash, status.value),
            )
        else:
            rows = self._execute_read(
                "SELECT * FROM follow_ups WHERE account_hash = ?",
                (account_hash,),
            )
        return [self._row_to_follow_up(r) for r in rows]

    def update_follow_up_status(self, follow_up_id: int, status: FollowUpStatus) -> None:
        """Update the status of a follow-up by its row ID."""
        now = datetime.now(tz=UTC).isoformat()
        self._execute_write(
            "UPDATE follow_ups SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now, follow_up_id),
        )

    # -- Priority senders --

    def add_priority_sender(self, sender: PrioritySender) -> None:
        """Add or update a priority sender."""
        now = datetime.now(tz=UTC).isoformat()
        self._execute_write(
            """INSERT INTO priority_senders (email_pattern, tier, label, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(email_pattern) DO UPDATE SET
                 tier = excluded.tier,
                 label = excluded.label""",
            (sender.email_pattern, sender.tier.value, sender.label, now),
        )

    def get_priority_senders(self) -> list[PrioritySender]:
        """Retrieve all priority senders."""
        rows = self._execute_read("SELECT * FROM priority_senders")
        return [
            PrioritySender(
                email_pattern=r["email_pattern"],
                tier=SenderTier(r["tier"]),
                label=r["label"],
            )
            for r in rows
        ]

    def remove_priority_sender(self, email_pattern: str) -> bool:
        """Remove a priority sender by pattern. Returns True if a row was deleted."""
        cursor = self._execute_write(
            "DELETE FROM priority_senders WHERE email_pattern = ?",
            (email_pattern,),
        )
        return cursor.rowcount > 0

    # -- Sync state --

    def get_sync_state(self, account_hash: str) -> SyncState | None:
        """Retrieve sync state for an account."""
        rows = self._execute_read(
            "SELECT * FROM sync_state WHERE account_hash = ?", (account_hash,)
        )
        if not rows:
            return None
        r = rows[0]
        return SyncState(
            account_email_hash=r["account_hash"],
            provider=r["provider"],
            sync_token=r["sync_token"],
            last_sync=datetime.fromisoformat(r["last_sync"]),
            messages_cached=r["messages_cached"],
        )

    def update_sync_state(self, state: SyncState) -> None:
        """Insert or update sync state for an account."""
        self._execute_write(
            """INSERT INTO sync_state
               (account_hash, provider, sync_token, last_sync, messages_cached)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(account_hash) DO UPDATE SET
                 provider = excluded.provider,
                 sync_token = excluded.sync_token,
                 last_sync = excluded.last_sync,
                 messages_cached = excluded.messages_cached""",
            (
                state.account_email_hash,
                state.provider,
                state.sync_token,
                state.last_sync.isoformat(),
                state.messages_cached,
            ),
        )

    # -- Maintenance --

    def evict_expired(self) -> int:
        """Remove expired scores (>24h) and old metadata (>30d). Returns count removed."""
        score_cutoff = (datetime.now(tz=UTC) - timedelta(hours=_SCORE_TTL_HOURS)).isoformat()
        meta_cutoff = (datetime.now(tz=UTC) - timedelta(days=_METADATA_TTL_DAYS)).isoformat()

        c1 = self._execute_write(
            "DELETE FROM importance_scores WHERE scored_at <= ?", (score_cutoff,)
        )
        c2 = self._execute_write("DELETE FROM message_cache WHERE cached_at <= ?", (meta_cutoff,))
        return (c1.rowcount or 0) + (c2.rowcount or 0)

    def reset(self) -> None:
        """Drop all tables and recreate them."""
        assert self._conn is not None
        with self._write_lock:
            self._conn.executescript(
                """
                DROP TABLE IF EXISTS importance_scores;
                DROP TABLE IF EXISTS follow_ups;
                DROP TABLE IF EXISTS priority_senders;
                DROP TABLE IF EXISTS sync_state;
                DROP TABLE IF EXISTS message_cache;
                """
            )
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    def row_count(self, table: str) -> int:
        """Return the number of rows in a table."""
        allowed = {
            "message_cache",
            "importance_scores",
            "follow_ups",
            "priority_senders",
            "sync_state",
        }
        if table not in allowed:
            raise ValueError(f"Unknown table: {table}")
        rows = self._execute_read(f"SELECT COUNT(*) AS cnt FROM {table}")  # noqa: S608
        return int(rows[0]["cnt"])

    @staticmethod
    def hash_address(address: str) -> str:
        """Return SHA256 hex digest of an email address."""
        return hashlib.sha256(address.encode()).hexdigest()

    # -- Internal helpers --

    def _row_to_score(self, row: dict[str, Any]) -> ImportanceScore:
        """Convert a database row to an ImportanceScore model."""
        signals_data = json.loads(row["signals"])
        signals = [ScoringSignal(**s) for s in signals_data]
        msg = self.get_cached_message(row["message_id"])
        thread_id = msg["thread_id"] if msg else ""
        return ImportanceScore(
            message_id=row["message_id"],
            thread_id=thread_id,
            score=row["score"],
            signals=signals,
            category=MessageCategory(row["category"]),
        )

    def _row_to_follow_up(self, row: dict[str, Any]) -> FollowUp:
        """Convert a database row to a FollowUp model."""
        return FollowUp(
            message_id=row["message_id"],
            thread_id=row["thread_id"],
            subject_hash=row["subject_hash"],
            sent_date=datetime.fromisoformat(row["sent_date"]),
            expected_reply_days=row["expected_reply_days"],
            deadline=(datetime.fromisoformat(row["deadline"]) if row["deadline"] else None),
            status=FollowUpStatus(row["status"]),
        )

    def _enforce_max_rows(self) -> None:
        """Evict oldest rows if message_cache exceeds the max row limit."""
        count = self.row_count("message_cache")
        if count > _MAX_MESSAGE_CACHE_ROWS:
            excess = count - _MAX_MESSAGE_CACHE_ROWS
            self._execute_write(
                """DELETE FROM message_cache WHERE message_id IN (
                     SELECT message_id FROM message_cache
                     ORDER BY cached_at ASC LIMIT ?
                   )""",
                (excess,),
            )
