"""OAuth 2.0 client credentials routes."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .config import Config
from .store import store_oauth_token

_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _base_url(allowed_origins: list[str]) -> str:
    """Return the first HTTPS non-local origin as the OAuth issuer base URL."""
    for origin in allowed_origins:
        if not origin.startswith("https://"):
            continue
        host = origin.removeprefix("https://").split(":")[0]
        if host not in _LOCAL_HOSTNAMES:
            return origin
    return allowed_origins[0] if allowed_origins else "http://localhost:8765"


def build_oauth_routes(config: Config) -> list[Route]:
    """Return Starlette Route objects for all OAuth endpoints."""
    base = _base_url(config.allowed_origins)

    async def oauth_protected_resource(_request: Request) -> Response:
        return JSONResponse({
            "resource": base,
            "authorization_servers": [base],
        })

    async def oauth_authorization_server(_request: Request) -> Response:
        return JSONResponse({
            "issuer": base,
            "token_endpoint": f"{base}/token",
            "grant_types_supported": ["client_credentials"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
        })

    async def oauth_token(request: Request) -> Response:
        form = await request.form()
        grant_type = form.get("grant_type") or ""
        if grant_type != "client_credentials":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

        client_id = str(form.get("client_id") or "")
        client_secret = str(form.get("client_secret") or "")

        client = config.oauth.clients.get(client_id)
        # Always compare to prevent timing-based enumeration of client IDs.
        expected = client.secret if client is not None else secrets.token_urlsafe(32)
        match = secrets.compare_digest(client_secret, expected)
        if client is None or not match:
            return JSONResponse({"error": "invalid_client"}, status_code=400)

        token = "oat_" + secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=config.oauth.token_ttl_seconds)
        ).isoformat(timespec="seconds")
        store_oauth_token(
            config.server.db_path,
            token,
            client_id,
            client.agent_id,
            expires_at,
        )
        return JSONResponse({
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": config.oauth.token_ttl_seconds,
        })

    async def oauth_register(_request: Request) -> Response:
        return JSONResponse(
            {
                "error": "registration_not_supported",
                "message": (
                    "Dynamic registration is disabled. "
                    "Request credentials from the administrator."
                ),
            },
            status_code=400,
        )

    return [
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server),
        Route("/token", oauth_token, methods=["POST"]),
        Route("/register", oauth_register, methods=["POST"]),
    ]
