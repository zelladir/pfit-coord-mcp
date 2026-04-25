"""Direct unit tests on the tool functions (contextvars set manually)."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from pfit_coord_mcp.models import (
    CoordAckInput,
    CoordPostInput,
    CoordReadInput,
    CoordStatusInput,
    CoordThreadsInput,
)
from pfit_coord_mcp.server import _current_agent, build_app, build_mcp
from pfit_coord_mcp.store import get_message


@pytest.fixture
def mcp_with_config(temp_config):
    return build_mcp(temp_config), temp_config


def _set_agent(agent_id: str):
    return _current_agent.set(agent_id)


def _get_tool(mcp, name):
    """Resolve a tool by name from the FastMCP instance.

    FastMCP stores tools internally; this peeks at its registry. If the
    SDK's internal API changes, swap to `mcp._tool_manager.get_tool(name)`
    or whatever the current accessor is — verify with introspection.
    """
    return mcp._tool_manager._tools[name].fn  # internal; acceptable for unit tests


@pytest.mark.asyncio
async def test_coord_post_inserts_and_returns_id(mcp_with_config):
    mcp, _ = mcp_with_config
    token = _set_agent("claude-code")
    try:
        result = await _get_tool(mcp, "coord_post")(
            CoordPostInput(to_agent="alex", kind="note", payload={"text": "hi"}),
            ctx=None,  # not used by handler
        )
        assert result["message_id"] > 0
        assert result["from_agent"] == "claude-code"
    finally:
        _current_agent.reset(token)


@pytest.mark.asyncio
async def test_coord_post_stop_and_ask_triggers_dry_run_notify(mcp_with_config):
    mcp, cfg = mcp_with_config
    token = _set_agent("codex")
    try:
        result = await _get_tool(mcp, "coord_post")(
            CoordPostInput(to_agent="alex", kind="stop_and_ask", payload={"question": "go?"}),
            ctx=None,
        )
        # Dry-run config: notified=False but reason indicates the rule fired
        assert result["notified"] is False
        assert result["notification_reason"] == "dry_run"
        row = get_message(cfg.server.db_path, result["message_id"])
        assert row["notified_at"] is not None
        assert row["notification_error"] == "dry_run"
    finally:
        _current_agent.reset(token)


@pytest.mark.asyncio
async def test_coord_read_returns_recipient_and_broadcast(mcp_with_config):
    mcp, _ = mcp_with_config
    # codex posts: one to alex, one to broadcast, one to claude-web
    poster = _set_agent("codex")
    try:
        for to in ("alex", "broadcast", "claude-web"):
            await _get_tool(mcp, "coord_post")(
                CoordPostInput(to_agent=to, kind="note", payload={}),
                ctx=None,
            )
    finally:
        _current_agent.reset(poster)
    # alex reads
    reader = _set_agent("alex")
    try:
        result = await _get_tool(mcp, "coord_read")(CoordReadInput(), ctx=None)
        targets = [m["to_agent"] for m in result["messages"]]
        assert "alex" in targets
        assert "broadcast" in targets
        assert "claude-web" not in targets
    finally:
        _current_agent.reset(reader)


@pytest.mark.asyncio
async def test_coord_threads_create_then_list_then_close(mcp_with_config):
    mcp, _ = mcp_with_config
    token = _set_agent("codex")
    try:
        created = await _get_tool(mcp, "coord_threads")(
            CoordThreadsInput(action="create", title="wave A"),
            ctx=None,
        )
        tid = created["thread_id"]
        listed = await _get_tool(mcp, "coord_threads")(
            CoordThreadsInput(action="list"),
            ctx=None,
        )
        assert any(t["id"] == tid for t in listed["threads"])
        await _get_tool(mcp, "coord_threads")(
            CoordThreadsInput(action="close", thread_id=tid),
            ctx=None,
        )
        listed_after = await _get_tool(mcp, "coord_threads")(
            CoordThreadsInput(action="list", include_closed=False),
            ctx=None,
        )
        assert all(t["id"] != tid for t in listed_after["threads"])
    finally:
        _current_agent.reset(token)


@pytest.mark.asyncio
async def test_coord_ack_idempotent(mcp_with_config):
    mcp, cfg = mcp_with_config
    poster = _set_agent("codex")
    try:
        posted = await _get_tool(mcp, "coord_post")(
            CoordPostInput(to_agent="alex", kind="note", payload={}),
            ctx=None,
        )
    finally:
        _current_agent.reset(poster)
    reader = _set_agent("alex")
    try:
        ack_input = CoordAckInput(message_ids=[posted["message_id"]])
        await _get_tool(mcp, "coord_ack")(ack_input, ctx=None)
        await _get_tool(mcp, "coord_ack")(ack_input, ctx=None)
        row = get_message(cfg.server.db_path, posted["message_id"])
        assert json.loads(row["read_by"]).count("alex") == 1
    finally:
        _current_agent.reset(reader)


@pytest.mark.asyncio
async def test_coord_status_posts_to_broadcast_no_notify(mcp_with_config):
    mcp, cfg = mcp_with_config
    token = _set_agent("claude-code")
    try:
        result = await _get_tool(mcp, "coord_status")(
            CoordStatusInput(summary="working on auth packet"),
            ctx=None,
        )
        row = get_message(cfg.server.db_path, result["message_id"])
        assert row["to_agent"] == "broadcast"
        assert row["kind"] == "status"
        assert row["notified_at"] is None  # status never notifies
    finally:
        _current_agent.reset(token)


def test_health_endpoint_returns_ok(temp_config):
    app = build_app(temp_config)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_mcp_endpoint_requires_auth(temp_config):
    app = build_app(temp_config)
    client = TestClient(app)
    r = client.post("/mcp", json={})
    assert r.status_code == 401
