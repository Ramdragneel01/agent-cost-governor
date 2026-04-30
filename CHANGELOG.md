# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/) and the project follows [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-01-XX

### Added
- FastAPI proxy with `POST /v1/proxy/{path:path}`.
- Per-tenant 24h sliding-window budget ledger (`agent_cost_governor.ledger.BudgetLedger`).
- YAML-driven policy: pricing, defaults, per-tenant budgets, downgrade rules (`agent_cost_governor.policy`).
- Pure-function routing decision: allow / downgrade / block (`agent_cost_governor.routing.decide`).
- Webhook alerter (Slack-compatible JSON body) with safe failure mode.
- Prometheus `/metrics`, JSON `/stats`, `/health`, `/ready`.
- Token → USD cost computation from upstream `usage` block.
- Test suite (≈ 27 tests across pricing, policy, ledger, routing, FastAPI proxy).
- Dockerfile (non-root uid 10001, healthcheck, python:3.11-slim base).
- `docker-compose.yml`, `examples/policy.yaml`, `.env.example`.
- CI: ruff lint, pytest with coverage, container smoke test, GHCR publish on tag.

[0.1.0]: https://github.com/Ramdragneel01/agent-cost-governor/releases/tag/v0.1.0
