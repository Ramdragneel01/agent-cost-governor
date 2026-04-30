# agent-cost-governor

> **FinOps proxy for LLM APIs.** Per-tenant daily budgets, automatic model downgrade when spend approaches budget, hard-stop at 100%, alerts to any webhook, and Prometheus metrics — all behind a single drop-in proxy URL.

[![CI](https://github.com/Ramdragneel01/agent-cost-governor/actions/workflows/ci.yml/badge.svg)](https://github.com/Ramdragneel01/agent-cost-governor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

---

## Why

Three things kill LLM unit economics in production:

1. A runaway agent that loops on `gpt-4o` overnight.
2. One enthusiastic tenant burning everyone else's budget.
3. Cost regressions invisible until the monthly bill arrives.

`agent-cost-governor` is the layer you wish you had wired in week one. Point your client at the governor instead of the upstream provider and get **per-tenant budgets, downgrade routing, and alerts** without touching application code.

---

## Quickstart

### Run with Docker

```bash
docker run --rm -p 8090:8090 \
  -e ACG_UPSTREAM_BASE_URL=https://api.openai.com \
  -e ACG_UPSTREAM_API_KEY=$OPENAI_API_KEY \
  -v "$PWD/examples/policy.yaml:/policy/policy.yaml:ro" \
  -e ACG_POLICY_PATH=/policy/policy.yaml \
  ghcr.io/ramdragneel01/agent-cost-governor:latest
```

Send a request as tenant `acme`:

```bash
curl http://localhost:8090/v1/proxy/v1/chat/completions \
  -H 'content-type: application/json' \
  -H 'x-acg-tenant: acme' \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role":"user","content":"hi"}]
  }'
```

When `acme` crosses 80% of its daily budget, subsequent `gpt-4o` calls are silently routed to `gpt-4o-mini`. At 100%, requests return `429 daily_budget_exhausted`.

### Run from source

```bash
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env  # set upstream key + policy path
python -m agent_cost_governor
```

### Compose

```bash
docker compose up --build
```

---

## Policy

A single YAML file declares pricing, defaults, and per-tenant budgets + downgrade rules. See [examples/policy.yaml](examples/policy.yaml).

```yaml
pricing:
  gpt-4o:      { input_per_1k: 0.005,   output_per_1k: 0.015 }
  gpt-4o-mini: { input_per_1k: 0.00015, output_per_1k: 0.0006 }

defaults:
  daily_budget_usd: 5.0
  alert_at_pct: 0.8
  block_at_pct: 1.0

tenants:
  acme:
    daily_budget_usd: 50
    downgrade:
      - { from: gpt-4o, to: gpt-4o-mini, when: budget_pct >= 0.8 }
```

---

## Endpoints

| Method | Path                       | Purpose                                       |
| ------ | -------------------------- | --------------------------------------------- |
| `GET`  | `/health`                  | Liveness                                      |
| `GET`  | `/ready`                   | Readiness                                     |
| `GET`  | `/stats`                   | JSON snapshot: decisions, recent audit, spend |
| `GET`  | `/metrics`                 | Prometheus exposition                         |
| `POST` | `/v1/proxy/{upstream-path}`| Forwarded to `ACG_UPSTREAM_BASE_URL/{path}`   |

---

## Configuration

All variables are prefixed with `ACG_`. See [.env.example](.env.example).

| Var                       | Default                  | Notes                                                |
| ------------------------- | ------------------------ | ---------------------------------------------------- |
| `ACG_UPSTREAM_BASE_URL`   | `https://api.openai.com` | Where requests are forwarded                         |
| `ACG_UPSTREAM_API_KEY`    | (empty)                  | Replaces client `Authorization` header               |
| `ACG_POLICY_PATH`         | `policy.yaml`            | Hot-loaded YAML policy                               |
| `ACG_TENANT_HEADER`       | `x-acg-tenant`           | Header that carries tenant id                        |
| `ACG_DEFAULT_TENANT`      | `default`                | Fallback when header is missing                      |
| `ACG_ALERT_WEBHOOK_URL`   | (empty)                  | Slack-compatible incoming webhook (or any JSON sink) |

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Coverage spans pricing math, policy parsing + downgrade rules, the budget ledger (sliding window), the routing decision engine, and the FastAPI proxy with mocked upstream (allow / downgrade / block / 502 / no-tenant-header).

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). TL;DR:

```
client ─▶ agent-cost-governor ─[allow/downgrade/block]─▶ upstream LLM API
              │
              ├── policy (YAML, hot-loaded)
              ├── budget ledger (24h sliding window)
              ├── routing decision (pure function)
              ├── alerts (webhook, fire-and-forget)
              └── /metrics, /stats, audit ring buffer
```

---

## Roadmap

- [ ] Redis-backed ledger for multi-replica deployments
- [ ] Per-tenant rate limiting (RPS / TPM)
- [ ] Streaming-response cost accounting
- [ ] OPA policy engine for richer rules (per-route, per-time-window)
- [ ] Native integration with [`rag-firewall`](https://github.com/Ramdragneel01/rag-firewall) so security and cost layers compose

Part of the **Production AI, From Zero** series — see [companion Medium article](https://medium.com/@RamPrakashD).

---

## License

[MIT](LICENSE) © Ram Prakash Dhulipudi
