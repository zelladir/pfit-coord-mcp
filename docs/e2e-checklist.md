# Post-deploy E2E checklist

Run after deploying the server (locally or via Cloudflare Tunnel) and
configuring all three agents. Replace `https://mcp.asquaredhome.com` with
`http://localhost:8765` if testing pre-tunnel.

## Server reachability
- [ ] `curl https://mcp.asquaredhome.com/health` → 200 with version JSON
- [ ] `curl https://mcp.asquaredhome.com/mcp` (no auth) → 401
- [ ] `curl -H "Authorization: Bearer <bad>" https://mcp.asquaredhome.com/mcp` → 401

## Agent: Claude Code
- [ ] Tools list includes `coord_post`, `coord_read`, `coord_threads`, `coord_ack`, `coord_status`
- [ ] "Use coord_status to broadcast that you're online" → posts a status message
- [ ] `coord-cli read --as-agent broadcast` shows the status

## Agent: Codex
- [ ] Tools list complete
- [ ] "Read the coord queue" → returns the broadcast status from Claude Code
- [ ] "Use coord_post to send a stop_and_ask to alex saying 'test ping'" → posts

## Pushover delivery
- [ ] Notification arrives on Alex's phone within 30s
- [ ] Title is `[codex] stop_and_ask`
- [ ] Body is `test ping`
- [ ] Priority is high (bypasses quiet hours)

## Agent: Claude Web (acting on Alex's behalf)
- [ ] "Anything in the coord queue for me?" → reads, finds the test ping
- [ ] "Reply to codex with answer 'noted'" → posts a kind=answer; no Pushover fires

## CLI
- [ ] `coord-cli tail --as-agent broadcast` shows live updates as messages flow

## Failure modes (sanity)
- [ ] Stop the server (`make down`); curl returns connection refused (or 502 via tunnel)
- [ ] Restart (`make up`); curl returns 200 again within ~10s
- [ ] Cloudflare Tunnel restart drops live SSE; clients reconnect on next tool call
