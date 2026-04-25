"""Notification module tests."""
from __future__ import annotations

import json

import pytest

from pfit_coord_mcp.config import Config, PushoverConfig, ServerConfig
from pfit_coord_mcp.notify import maybe_notify, rule_matches
from pfit_coord_mcp.store import get_message, post_message


@pytest.fixture
def dry_run_config(temp_db):
    return Config(
        server=ServerConfig(port=8765, db_path=temp_db),
        tokens={},
        pushover=PushoverConfig(dry_run=True, user_key="", app_token=""),
        allowed_origins=[],
    )


def test_rule_matches_stop_and_ask_to_anyone():
    assert rule_matches(kind="stop_and_ask", to_agent="claude-web") is True
    assert rule_matches(kind="stop_and_ask", to_agent="alex") is True


def test_rule_matches_handoff_only_to_alex():
    assert rule_matches(kind="handoff", to_agent="alex") is True
    assert rule_matches(kind="handoff", to_agent="claude-web") is False


def test_rule_matches_status_never():
    assert rule_matches(kind="status", to_agent="alex") is False


@pytest.mark.asyncio
async def test_maybe_notify_dry_run_marks_notified_without_http(temp_db, dry_run_config):
    msg_id = post_message(temp_db, "codex", "alex", "stop_and_ask", json.dumps({"text": "ping"}), None)
    result = await maybe_notify(dry_run_config, msg_id)
    assert result.notified is False
    assert result.reason == "dry_run"
    row = get_message(temp_db, msg_id)
    assert row["notified_at"] is not None
    assert row["notification_error"] == "dry_run"


@pytest.mark.asyncio
async def test_maybe_notify_skips_already_notified(temp_db, dry_run_config):
    msg_id = post_message(temp_db, "codex", "alex", "stop_and_ask", "{}", None)
    await maybe_notify(dry_run_config, msg_id)  # first call sets notified_at
    result = await maybe_notify(dry_run_config, msg_id)
    assert result.reason == "already_notified"


@pytest.mark.asyncio
async def test_maybe_notify_skips_rule_mismatch(temp_db, dry_run_config):
    msg_id = post_message(temp_db, "codex", "claude-web", "status", "{}", None)
    result = await maybe_notify(dry_run_config, msg_id)
    assert result.reason == "rule_not_matched"
    row = get_message(temp_db, msg_id)
    assert row["notified_at"] is None  # left untouched
