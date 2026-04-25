"""SQLite store tests."""
from __future__ import annotations

import sqlite3

from pfit_coord_mcp.store import init_db


def test_init_db_creates_schema(tmp_path):
    """init_db creates messages, threads, meta tables and indexes."""
    db = tmp_path / "c.db"
    init_db(str(db))
    conn = sqlite3.connect(str(db))
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert {"messages", "threads", "meta"} <= tables
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        assert "idx_messages_to_agent" in indexes
        assert "idx_messages_thread" in indexes
        assert "idx_messages_timestamp" in indexes
    finally:
        conn.close()


def test_init_db_is_idempotent(tmp_path):
    """Running init_db twice on the same file does not error."""
    db = tmp_path / "c.db"
    init_db(str(db))
    init_db(str(db))


def test_init_db_enables_wal_mode(tmp_path):
    """init_db sets journal_mode=WAL for concurrent reader/writer safety."""
    db = tmp_path / "c.db"
    init_db(str(db))
    conn = sqlite3.connect(str(db))
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()
