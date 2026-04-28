"""OAuth 2.0 client credentials route tests."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from pfit_coord_mcp.config import Config, OAuthClientConfig, OAuthConfig, PushoverConfig, ServerConfig
from pfit_coord_mcp.server import build_app
from pfit_coord_mcp.store import init_db


@pytest.fixture
def oauth_config(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    return Config(
        server=ServerConfig(port=8765, db_path=db),
        tokens={"static-tok-cc": "claude-code"},
        pushover=PushoverConfig(dry_run=True),
        allowed_origins=[
            "https://mcp.asquaredhome.com",
            "http://localhost:8765",
            "http://127.0.0.1:8765",
        ],
        oauth=OAuthConfig(
            token_ttl_seconds=3600,
            clients={
                "ccw_testclient": OAuthClientConfig(secret="ccs_testsecret", agent_id="claude-web")
            },
        ),
    )


def test_oauth_protected_resource(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    data = r.json()
    assert data["resource"] == "https://mcp.asquaredhome.com"
    assert "https://mcp.asquaredhome.com" in data["authorization_servers"]


def test_oauth_authorization_server(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    data = r.json()
    assert data["issuer"] == "https://mcp.asquaredhome.com"
    assert data["token_endpoint"] == "https://mcp.asquaredhome.com/token"
    assert "authorization_endpoint" not in data
    assert "client_credentials" in data["grant_types_supported"]


def test_discovery_requires_no_auth(oauth_config):
    client = TestClient(build_app(oauth_config))
    assert client.get("/.well-known/oauth-protected-resource").status_code == 200
    assert client.get("/.well-known/oauth-authorization-server").status_code == 200


def test_token_valid_credentials(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.post("/token", data={
        "grant_type": "client_credentials",
        "client_id": "ccw_testclient",
        "client_secret": "ccs_testsecret",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 3600
    assert data["access_token"].startswith("oat_")


def test_token_wrong_secret(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.post("/token", data={
        "grant_type": "client_credentials",
        "client_id": "ccw_testclient",
        "client_secret": "wrong_secret",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client"


def test_token_unknown_client_id(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.post("/token", data={
        "grant_type": "client_credentials",
        "client_id": "ccw_unknown",
        "client_secret": "anything",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client"


def test_token_wrong_grant_type(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.post("/token", data={
        "grant_type": "authorization_code",
        "client_id": "ccw_testclient",
        "client_secret": "ccs_testsecret",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"


def test_token_endpoint_requires_no_auth(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.post("/token", data={
        "grant_type": "client_credentials",
        "client_id": "ccw_testclient",
        "client_secret": "ccs_testsecret",
    })
    assert r.status_code != 401


def test_register_returns_400(oauth_config):
    client = TestClient(build_app(oauth_config))
    r = client.post("/register", json={"client_name": "some-connector"})
    assert r.status_code == 400
    assert r.json()["error"] == "registration_not_supported"


def test_oauth_token_authenticates_on_mcp(oauth_config):
    # raise_server_exceptions=False: the MCP session manager raises RuntimeError
    # when the lifespan task group is not running (TestClient without lifespan).
    # That becomes a 500, not a 401 — auth passed.
    client = TestClient(build_app(oauth_config), raise_server_exceptions=False)
    r = client.post("/token", data={
        "grant_type": "client_credentials",
        "client_id": "ccw_testclient",
        "client_secret": "ccs_testsecret",
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    r2 = client.post("/mcp", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code != 401, f"Expected auth to pass, got 401. Token: {token}"


def test_static_bearer_token_still_works(oauth_config):
    client = TestClient(build_app(oauth_config), raise_server_exceptions=False)
    assert client.get("/health").status_code == 200
    r2 = client.post("/mcp", headers={"Authorization": "Bearer static-tok-cc"})
    assert r2.status_code != 401
