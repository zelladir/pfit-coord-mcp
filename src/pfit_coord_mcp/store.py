"""SQLite-backed message store."""
from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          TEXT NOT NULL,
    from_agent         TEXT NOT NULL,
    to_agent           TEXT NOT NULL,
    thread_id          TEXT,
    kind               TEXT NOT NULL,
    payload            TEXT NOT NULL,
    read_by            TEXT NOT NULL DEFAULT '[]',
    notified_at        TEXT,
    notification_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_to_agent  ON messages(to_agent);
CREATE INDEX IF NOT EXISTS idx_messages_thread    ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    closed      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init_db(path: str) -> None:
    """Create the SQLite database (if needed) and apply schema. Idempotent."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _connect(path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


RECIPIENT_BROADCAST = "broadcast"


def post_message(
    db_path: str,
    from_agent: str,
    to_agent: str,
    kind: str,
    payload: str,
    thread_id: str | None,
) -> int:
    """Insert a message and return its new id."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO messages (timestamp, from_agent, to_agent, thread_id, kind, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_now_iso(), from_agent, to_agent, thread_id, kind, payload),
        )
        new_id = cur.lastrowid
        if new_id is None:  # pragma: no cover  # SQLite always returns an id for AUTOINCREMENT
            raise RuntimeError("SQLite did not return a lastrowid")
        return int(new_id)


def get_message(db_path: str, message_id: int) -> sqlite3.Row | None:
    with _connect(db_path) as conn:
        cur = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
        row: sqlite3.Row | None = cur.fetchone()
        return row


def ack_messages(db_path: str, message_ids: Sequence[int], by_agent: str) -> int:
    """Append `by_agent` to each message's `read_by` JSON array. Idempotent."""
    if not message_ids:
        return 0
    with _connect(db_path) as conn:
        n = 0
        for mid in message_ids:
            row = conn.execute("SELECT read_by FROM messages WHERE id = ?", (mid,)).fetchone()
            if row is None:
                continue
            existing = json.loads(row["read_by"])
            if by_agent not in existing:
                existing.append(by_agent)
                conn.execute(
                    "UPDATE messages SET read_by = ? WHERE id = ?",
                    (json.dumps(existing), mid),
                )
            n += 1
        return n


def mark_notified(db_path: str, message_id: int, error: str | None) -> None:
    """Set notified_at = now and record any error string."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE messages SET notified_at = ?, notification_error = ? WHERE id = ?",
            (_now_iso(), error, message_id),
        )


# Server-enforced notification rules. (kind, recipient_predicate) -> priority
NOTIFY_KIND_RULES = {
    "stop_and_ask": "*",  # any recipient
    "handoff": "alex",  # only when addressed to alex
    "task_complete": "alex",
    "question": "alex",
}


def pending_notifications(db_path: str) -> list[sqlite3.Row]:
    """Return messages eligible for notification (not yet notified)."""
    parts: list[str] = []
    params: list[Any] = []
    for kind, recipient in NOTIFY_KIND_RULES.items():
        if recipient == "*":
            parts.append("kind = ?")
            params.append(kind)
        else:
            parts.append("(kind = ? AND to_agent = ?)")
            params.extend([kind, recipient])
    where = "(" + " OR ".join(parts) + ") AND notified_at IS NULL"
    with _connect(db_path) as conn:
        return list(conn.execute(
            f"SELECT * FROM messages WHERE {where} ORDER BY id ASC", params
        ).fetchall())


def read_messages(
    db_path: str,
    to_agent: str,
    since_id: int | None = None,
    thread_id: str | None = None,
    kinds: Sequence[str] | None = None,
    unread_only: bool = False,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Return messages addressed to `to_agent` (or to broadcast).

    Filters compose with AND. `unread_only` excludes rows whose `read_by` JSON
    array already contains `to_agent`.
    """
    capped_limit = min(max(limit, 1), 200)
    clauses = ["(to_agent = ? OR to_agent = ?)"]
    params: list[Any] = [to_agent, RECIPIENT_BROADCAST]
    if since_id is not None:
        clauses.append("id > ?")
        params.append(since_id)
    if thread_id is not None:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    if kinds:
        placeholders = ",".join("?" for _ in kinds)
        clauses.append(f"kind IN ({placeholders})")
        params.extend(kinds)
    if unread_only:
        # SQLite JSON1 — `json_each(read_by)` exposes the array elements;
        # the NOT EXISTS keeps rows where to_agent is not yet in the array.
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM json_each(read_by) WHERE value = ?)"
        )
        params.append(to_agent)

    sql = (
        "SELECT * FROM messages WHERE " + " AND ".join(clauses)
        + " ORDER BY id ASC LIMIT ?"
    )
    params.append(capped_limit)
    with _connect(db_path) as conn:
        return list(conn.execute(sql, params).fetchall())


def create_thread(db_path: str, title: str, created_by: str) -> str:
    """Create a thread with a short URL-safe slug ID."""
    tid = "thr-" + secrets.token_urlsafe(6)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO threads (id, title, created_by, created_at, closed)"
            " VALUES (?, ?, ?, ?, 0)",
            (tid, title, created_by, _now_iso()),
        )
    return tid


def list_threads(db_path: str, include_closed: bool = False) -> list[sqlite3.Row]:
    """Return threads ordered by creation time descending."""
    sql = "SELECT * FROM threads"
    if not include_closed:
        sql += " WHERE closed = 0"
    sql += " ORDER BY created_at DESC"
    with _connect(db_path) as conn:
        return list(conn.execute(sql).fetchall())


def close_thread(db_path: str, thread_id: str) -> None:
    """Mark a thread as closed."""
    with _connect(db_path) as conn:
        conn.execute("UPDATE threads SET closed = 1 WHERE id = ?", (thread_id,))
