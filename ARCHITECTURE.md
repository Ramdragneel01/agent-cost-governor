# Architecture — agent-cost-governor

## Goal

Stop runaway LLM spend without engineers having to remember to. Make budget enforcement, downgrade routing, and alerts a property of *infrastructure*, not application code.

## Component View

```
                ┌─────────────────────────────────────────────────┐
                │              agent-cost-governor                │
 client ──HTTP──▶                                                 │
                │  ┌──────────┐   ┌──────────┐   ┌──────────────┐ │──▶ upstream LLM API
                │  │ tenantize │──▶│  decide  │──▶│ forward+book │ │
                │  └──────────┘   └──────────┘   └──────────────┘ │
                │       ▲              ▲                ▲         │
                │   header lookup   policy + ledger    cost        │
                │                                  accounting      │
                │                          │                       │
                │                          ▼                       │
                │                    ┌─────────────┐               │
                │                    │  Alerter    │──▶ Webhook    │
                │                    └─────────────┘               │
                │                          │                       │
                │                          ▼                       │
                │                MetricsStore, audit ring          │
                └─────────────────────────────────────────────────┘
```

## Module Map

| Module                                | Responsibility                                                |
| ------------------------------------- | ------------------------------------------------------------- |
| `agent_cost_governor.app`             | FastAPI app, proxy route, header normalization                 |
| `agent_cost_governor.config`          | Pydantic Settings, env-driven config                          |
| `agent_cost_governor.policy`          | YAML loader: pricing, tenants, downgrade rules, defaults      |
| `agent_cost_governor.pricing`         | Token → USD cost math; request/response token extraction      |
| `agent_cost_governor.ledger`          | Thread-safe 24h sliding-window per-tenant spend ledger        |
| `agent_cost_governor.routing`         | Pure-function decision: allow / downgrade / block             |
| `agent_cost_governor.alerts`          | Webhook fire-and-forget alerter (Slack-compatible body)       |
| `agent_cost_governor.metrics`         | Counters, audit ring, Prometheus exposition                   |

## Request Flow

1. Client `POST /v1/proxy/<upstream-path>` with a chat-completion JSON body.
2. JSON parsed; non-JSON or non-object bodies → `400`.
3. Tenant id read from `ACG_TENANT_HEADER` (default `x-acg-tenant`); falls back to `ACG_DEFAULT_TENANT`.
4. `routing.decide(payload, tenant, policy, ledger)` returns one of:
   - `allow`     — forward as-is
   - `downgrade` — rewrite `model` field, then forward
   - `block`     — return `429 daily_budget_exhausted`
5. On forward, hop-by-hop headers and client `Authorization` are stripped; firewall-managed upstream key is injected.
6. After upstream responds, the `usage` block is read and exact USD cost is computed via `pricing.estimate_cost_usd` and recorded against the tenant in `ledger`.
7. Audit event written; alert fires if `used_pct >= alert_at_pct`.

Every step also writes a counter to `MetricsStore` exposed at `/metrics`.

## Key Design Decisions

### 1. Pre-flight decision, post-flight accounting

The decision (allow / downgrade / block) uses spend *up to but not including* the current request. The current request's cost is added to the ledger only after the upstream returns its `usage` block. This avoids the chicken-and-egg of "how do we count what we haven't spent yet" while still hard-stopping at 100%.

### 2. Pure-function decision engine

`routing.decide` takes `(payload, tenant, policy, ledger)` and returns a `RoutingDecision`. No HTTP, no async, no globals. Every routing rule is unit-testable in milliseconds.

### 3. Policy as YAML, not code

Operators rotate budgets and downgrade rules without redeploying. YAML is parsed into typed dataclasses, so misconfigurations fail loudly at load time, not at request time.

### 4. Sliding 24h window, not calendar day

Calendar-day rollovers create thundering herds at midnight UTC. The ledger uses a true rolling 24h window so spend amortizes naturally.

### 5. Alerts are fire-and-forget

Alerting must never break the proxy. Webhook errors are logged and swallowed. A queue-backed alerter is the v0.2 path.

### 6. In-memory ledger for v0.1

Single replica is fine for most teams starting out. Multi-replica deployments need a Redis-backed `BudgetLedger` — the protocol is already shaped for it; only the storage layer changes.

## Trade-offs Recorded for v0.2

- **No streaming-response accounting.** Streaming responses do not include a `usage` block until completion; v0.2 will buffer-and-tally on close.
- **No per-route rules.** Today the policy is global per-tenant. Per-endpoint rules (e.g., expensive `tools/code-interpreter`) need a richer matcher.
- **In-memory state.** Counters and ledger reset on restart. Acceptable for v0.1; OTLP + Redis path is the long-term shape.

## Operational Targets (v0.1)

- p95 added latency: ≤ 35ms
- Image size: ≤ 200MB
- Memory: ≤ 256MB at idle
- Test coverage: ≥ 85% on `src/agent_cost_governor/`

## Extension Points

- `ledger.BudgetLedger` — swap for a Redis variant (same interface)
- `alerts.Alerter` — Slack blocks, PagerDuty, queue-backed
- `policy._parse_rule` — richer rule DSL (e.g., `time_of_day`, `model_class`)
