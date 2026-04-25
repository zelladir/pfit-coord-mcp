# Azure Migration Plan

When local + Cloudflare Tunnel becomes a constraint (uptime, multi-developer
access, etc.), migrate to Azure App Service or Container Apps. This doc
captures the migration path. **Not yet built** — when the time comes, this
becomes the spec.

## What changes

- Server runs as a containerized App Service or Container App, not locally.
- DNS flips from Cloudflare Tunnel to Azure Front Door (or direct CNAME to
  the App Service hostname).
- Pushover token moves from local `config.toml` into Azure Key Vault.
- SQLite stays for now; Azure SQL migration is a separate decision.

## What stays the same

- Server code: zero changes.
- Tool API: zero changes.
- Agent configs: only the URL changes if the hostname changes (it doesn't if
  `mcp.asquaredhome.com` stays).

## Steps

1. Build container, push to Azure Container Registry.
2. Create App Service plan (B1 ~$13/mo, or P0v3 if usage justifies).
3. Deploy container to App Service with health-check path `/health`.
4. Mount Azure Files share at `/app/data` for SQLite persistence.
5. Add Pushover credentials as App Service config (or Key Vault references).
6. Verify: `curl https://<app-service>.azurewebsites.net/health`.
7. Update Cloudflare DNS: change CNAME for `mcp.asquaredhome.com` from the
   tunnel to the App Service hostname.
8. Confirm traffic flows; tear down the local Cloudflare Tunnel.

## Cost estimate

| Component                          | Cost (USD/mo) |
| ---------------------------------- | ------------- |
| App Service B1                     | ~$13          |
| Azure Files (small)                | ~$1           |
| Container Registry Basic           | ~$5           |
| **Total**                          | **~$19**      |

## Alternative: Container Apps with scale-to-zero

Cheaper for low-traffic personal use (~$5–10/mo). Trade-off: cold-start
latency on the first request after idle. Probably the right pick for v1
production.
