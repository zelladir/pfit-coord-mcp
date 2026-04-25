"""Auth middleware tests."""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from pfit_coord_mcp.auth import (
    AGENT_ID_STATE_KEY,
    BearerTokenMiddleware,
    OriginAllowlistMiddleware,
)


def _build_app(token_map: dict[str, str], allowed_origins: list[str] | None = None):
    """Tiny app that echoes the resolved agent_id from request.state."""
    async def echo(request: Request) -> JSONResponse:
        agent_id = getattr(request.state, AGENT_ID_STATE_KEY, None)
        return JSONResponse({"agent_id": agent_id})

    middleware = []
    if allowed_origins is not None:
        middleware.append(Middleware(OriginAllowlistMiddleware, allowed_origins=allowed_origins))
    middleware.append(Middleware(BearerTokenMiddleware, token_map=token_map))

    return Starlette(
        routes=[Route("/echo", echo, methods=["GET", "POST"])],
        middleware=middleware,
    )


def test_missing_authorization_returns_401():
    client = TestClient(_build_app({"abc": "claude-web"}))
    r = client.get("/echo")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_malformed_authorization_returns_401():
    client = TestClient(_build_app({"abc": "claude-web"}))
    r = client.get("/echo", headers={"Authorization": "Token abc"})
    assert r.status_code == 401


def test_unknown_token_returns_401():
    client = TestClient(_build_app({"abc": "claude-web"}))
    r = client.get("/echo", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_valid_token_attaches_agent_id():
    client = TestClient(_build_app({"abc": "claude-web"}))
    r = client.get("/echo", headers={"Authorization": "Bearer abc"})
    assert r.status_code == 200
    assert r.json() == {"agent_id": "claude-web"}


def test_health_endpoint_bypasses_auth():
    """Requests to /health pass through both middlewares unauthenticated."""
    from pfit_coord_mcp.auth import HEALTH_PATH

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[Route(HEALTH_PATH, health)],
        middleware=[Middleware(BearerTokenMiddleware, token_map={"abc": "claude-web"})],
    )
    client = TestClient(app)
    assert client.get(HEALTH_PATH).status_code == 200
