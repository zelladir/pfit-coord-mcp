# pfit-coord-mcp

Coordination MCP server hosting a shared message queue between Claude Web,
Claude Code, and Codex. STOP-AND-ASK and handoff-to-alex messages page Alex's
phone via Pushover.

## What it does

```
                ┌─────────────┐
                │ Claude Web  │ ─┐
                └─────────────┘  │
                ┌─────────────┐  │   bearer auth
                │ Claude Code │ ─┼──────────────►  ┌──────────────────┐
                └─────────────┘  │   streamable    │  pfit-coord-mcp  │
                ┌─────────────┐  │     HTTP        │  (FastMCP +      │
                │   Codex     │ ─┘                  │   SQLite + auth) │
                └─────────────┘                     └────────┬─────────┘
                                                             │
                            ┌────────────────────────────────┤
                            │                                │
                            ▼                                ▼
                  ┌─────────────────┐              ┌──────────────────┐
                  │ Pushover (push  │              │ coord-cli (alex  │
                  │ to Alex's phone)│              │ reads queue from │
                  └─────────────────┘              │ host shell)      │
                                                   └──────────────────┘

   Public URL: https://mcp.asquaredhome.com  ←  Cloudflare Tunnel  ←  localhost:8765
```

Five MCP tools:

- `coord_post` — post a message addressed to one of the agents (or `broadcast`)
- `coord_read` — read messages addressed to your agent ID + broadcast
- `coord_threads` — create / list / close coordination threads
- `coord_ack` — mark messages as read
- `coord_status` — lightweight status heartbeat (broadcast, no notification)

Server-enforced notification rules:

| Kind            | Recipient | Pushover priority |
| --------------- | --------- | ----------------- |
| `stop_and_ask`  | any       | high (bypass DND) |
| `handoff`       | `alex`    | normal            |
| `task_complete` | `alex`    | normal            |
| `question`      | `alex`    | normal            |
| anything else   | —         | none              |

## Quickstart (host)

```bash
git clone https://github.com/zelladir/pfit-coord-mcp
cd pfit-coord-mcp

# 1. Generate three bearer tokens
python -c "import secrets; print(secrets.token_urlsafe(32))"  # x3

# 2. Copy + edit config
cp config.toml.example config.toml
# Paste tokens into [tokens] (replace REPLACE_WITH_GENERATED_TOKEN_*)
# Paste your Pushover user_key + app_token into [pushover]
# (If creds are empty, server auto-forces dry_run=true.)

# 3. Boot
make build
make up

# 4. Health check
curl http://localhost:8765/health

# 5. Optional: set up Cloudflare Tunnel for public URL
# See docs/cloudflare-tunnel.md
```

## Setup docs

- [Claude Code](docs/claude-code-setup.md)
- [Codex](docs/codex-setup.md)
- [Claude Web (claude.ai connectors)](docs/claude-web-connector-setup.md)
- [Cloudflare Tunnel](docs/cloudflare-tunnel.md)
- [Post-deploy E2E checklist](docs/e2e-checklist.md)
- [Azure migration plan (future)](docs/azure-migration.md)

## CLI

```bash
coord-cli read --as-agent alex                  # show alex's queue
coord-cli read --thread thr-abcd                # filter to a thread
coord-cli tail --as-agent broadcast             # follow live
coord-cli post --from-agent alex --to codex \
              --kind answer --text "yes"        # admin post (bypasses MCP auth)
coord-cli threads                               # list open threads
coord-cli thread-create --title "wave A"        # create
```

## Architecture

- **Transport:** MCP streamable HTTP (single endpoint, POST + GET, SSE for streamed responses).
- **Auth:** Bearer token at the Starlette middleware layer (3 tokens, one per
  client identity). The `alex` identity is recipient-only — humans don't auth
  to the MCP; Alex reads via the CLI.
- **DNS-rebinding defense:** Origin allowlist middleware (per MCP spec MUST).
- **Store:** SQLite WAL mode at `./data/coord.db`. Backup is "copy the file."
  No replication. If the DB dies, you've lost a coordination log, not real work.
- **Notifications:** Server-enforced rules dispatch via Pushover. Each message
  pushes at most once (`notified_at` is set even on failure to prevent retry loops).

## Safety notes

- **Tokens are secrets.** Don't commit `config.toml`. Rotate immediately if leaked.
- **The DB has all coordination history.** Treat it like a private log.
- **The tunnel exposes the server publicly.** Bearer auth is the only protection;
  rotate tokens if any client device is compromised.
- **Pushover usage limits change May 1, 2026** (per Pushover banner at build
  time). If you start hitting unexpected 429s, check the Pushover dashboard.

## Development

```bash
make install      # install in editable mode with dev deps
make test         # full pytest suite
make lint         # ruff check + format check
make typecheck    # mypy strict
make format       # ruff format
```

## License

MIT — see [LICENSE](LICENSE).
