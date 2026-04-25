"""Pydantic input/output models for MCP tool calls."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ValidRecipient = Literal["claude-web", "claude-code", "codex", "alex", "broadcast"]
ValidKind = Literal[
    "status",
    "question",
    "answer",
    "handoff",
    "note",
    "stop_and_ask",
    "task_complete",
]


class CoordPostInput(BaseModel):
    to_agent: ValidRecipient
    kind: ValidKind
    payload: dict[str, Any]
    thread_id: str | None = None


class CoordReadInput(BaseModel):
    since_id: int | None = None
    thread_id: str | None = None
    kinds: list[ValidKind] | None = None
    unread_only: bool = False
    limit: int = 50


class CoordThreadsInput(BaseModel):
    action: Literal["create", "list", "close"]
    thread_id: str | None = None
    title: str | None = None
    include_closed: bool = False


class CoordAckInput(BaseModel):
    message_ids: list[int]


class CoordStatusInput(BaseModel):
    summary: str = Field(..., max_length=500)
    thread_id: str | None = None


class NotifyResult(BaseModel):
    notified: bool
    error: str | None = None
    reason: str | None = None
