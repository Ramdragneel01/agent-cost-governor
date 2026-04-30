# Security Policy — agent-cost-governor

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email: **ramprakashdhulipudi@gmail.com**

Include:
- Description and impact
- Reproduction steps or proof-of-concept
- Affected version / commit SHA

We will acknowledge within 72 hours and aim to provide a remediation plan within 7 days for high-severity issues.

## Threat Model (v0.1)

### In Scope

| Class | Surface | Mitigation |
|---|---|---|
| Tenant impersonation via spoofed header | `tenant_header` | Operate behind an authenticating gateway that validates and injects the tenant header server-side; never let clients pick their own tenant in production |
| Credential forwarding from clients to upstream | Proxy | Client `Authorization` is stripped; governor owns the upstream key |
| Policy file tampering | `policy.yaml` | Treat as security-sensitive — mount read-only; protect with file ACLs / secret manager |
| Webhook abuse (alert spam) | `WebhookAlerter` | Errors are swallowed; rate limiting is the operator's responsibility on the receiver side |
| Block-reason oracle | error responses | Errors are generic; only the policy code (e.g., `daily_budget_exhausted`) is exposed |

### Out of Scope (v0.1)

- **Multi-replica accounting integrity** — the in-memory ledger is per-process. Two replicas double the budget. v0.2 ships a Redis ledger.
- **Streaming response cost** — no `usage` block until close; not counted against the budget yet.
- **Per-tenant secret separation** — v0.1 uses one upstream key for all tenants. Per-tenant keys are roadmap.
- **Network DDoS** — front with a CDN / WAF.

## Hardening Checklist

If you deploy `agent-cost-governor`:

- [ ] Run as non-root (provided in the Dockerfile).
- [ ] Inject the tenant header at an *authenticated* gateway, not from clients.
- [ ] Mount `policy.yaml` read-only.
- [ ] Restrict `/metrics` to private network.
- [ ] Rotate `ACG_UPSTREAM_API_KEY` via your secret manager.
- [ ] Treat the audit log and `/stats` as security-sensitive — they reveal tenant spend patterns.

## Dependency Security

- Runtime deps pinned in `requirements.txt`.
- `pip-audit` in CI (planned for v0.2).
- Renovate bot enabled day 1.
