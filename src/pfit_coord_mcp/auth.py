"""Starlette middleware: Bearer-token auth + Origin allowlist."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

AGENT_ID_STATE_KEY = "agent_id"
HEALTH_PATH = "/health"


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Validate `Authorization: Bearer <token>`; attach agent_id to request.state.

    The /health endpoint is unauthenticated (bypass).
    """

    def __init__(self, app: ASGIApp, token_map: dict[str, str]) -> None:
        super().__init__(app)
        self.token_map = token_map

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == HEALTH_PATH:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse(
                {"error": "unauthorized", "message": "Bearer token required"},
                status_code=401,
            )
        agent_id = self.token_map.get(token)
        if agent_id is None:
            return JSONResponse(
                {"error": "unauthorized", "message": "Unknown bearer token"},
                status_code=401,
            )
        setattr(request.state, AGENT_ID_STATE_KEY, agent_id)
        return await call_next(request)


class OriginAllowlistMiddleware(BaseHTTPMiddleware):
    """DNS-rebinding defense per MCP streamable HTTP spec.

    Rules:
    - Requests with no Origin header pass through (CLI / curl / non-browser).
    - Requests with an Origin header must match one of `allowed_origins`.
    - /health is exempt.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == HEALTH_PATH:
            return await call_next(request)
        origin = request.headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            return JSONResponse(
                {"error": "forbidden_origin", "message": f"Origin not allowed: {origin}"},
                status_code=403,
            )
        return await call_next(request)
