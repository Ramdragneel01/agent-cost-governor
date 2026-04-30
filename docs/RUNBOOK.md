# Runbook — agent-cost-governor

Operational guide for on-call engineers.

## 1. Deploy

### Container

```bash
docker run -d --name acg --restart unless-stopped \
  -p 8090:8090 \
  -e ACG_UPSTREAM_BASE_URL=https://api.openai.com \
  -e ACG_UPSTREAM_API_KEY=$OPENAI_API_KEY \
  -e ACG_ALERT_WEBHOOK_URL=$SLACK_WEBHOOK \
  -v /etc/acg/policy.yaml:/policy/policy.yaml:ro \
  -e ACG_POLICY_PATH=/policy/policy.yaml \
  ghcr.io/ramdragneel01/agent-cost-governor:latest
```

Verify:

```bash
curl -fsS http://localhost:8090/health
curl -fsS http://localhost:8090/metrics | grep acg_decisions_total
```

### Kubernetes

A starter manifest is left for the operator (Deployment + Service + ConfigMap mounting `policy.yaml`). Set `replicas: 1` until the Redis ledger lands in v0.2.

## 2. Rotate Upstream API Key

1. Generate a new key in the upstream provider's console.
2. Update the secret manager entry / `ACG_UPSTREAM_API_KEY`.
3. Rolling-restart the pod / container.
4. Watch `/metrics` for `acg_upstream_errors_total` to ensure the new key works.
5. Revoke the old key in the provider console.

## 3. Update Budgets

`policy.yaml` is parsed at process start. To change a budget:

1. Edit `policy.yaml` in source control.
2. Apply: rolling restart (single replica) or trigger a deploy.
3. Confirm via `GET /stats` — the `policy_summary` block reflects the new numbers.

> ⚠️  Budgets are **enforced from now**, not retroactively. A tenant that already burned through its old budget remains blocked until the rolling 24h window decays.

## 4. Tune Downgrade Rules

```yaml
tenants:
  acme:
    downgrade:
      - { from: gpt-4o, to: gpt-4o-mini, when: budget_pct >= 0.8 }
```

Lower the threshold to be more aggressive (downgrade earlier). Multiple rules with different thresholds can target the same `from` model — the highest matched threshold wins, so order does not matter.

## 5. Alert Playbooks

### `daily_budget_exhausted` (HTTP 429 spike)

1. Identify the tenant from `/stats` audit.
2. Decide: raise budget temporarily, or wait for the 24h window to decay.
3. If raising: edit `policy.yaml`, redeploy.

### Webhook flood

If `ACG_ALERT_WEBHOOK_URL` is firing too often:
- Increase `alert_at_pct` in defaults / per tenant.
- Add deduplication on the receiver side (Slack supports `thread_ts`).

### Upstream errors (502 from governor)

- `docker logs acg | grep upstream_error`
- Confirm `ACG_UPSTREAM_BASE_URL` and key.
- If upstream provider is degraded, governor passes through. Spend is not booked for failed requests.

## 6. Key Metrics

| Metric                          | Type    | Meaning                                   |
| ------------------------------- | ------- | ----------------------------------------- |
| `acg_decisions_total{result}`   | counter | result ∈ {allow, downgrade, block}        |
| `acg_cost_usd_total{tenant}`    | counter | Cumulative USD spend recorded by governor |

Suggested alerts:
- `rate(acg_decisions_total{result="block"}[5m]) > 0`
- `increase(acg_cost_usd_total[1h]) > <hourly_threshold>`

## 7. Backup / Restore

The in-memory ledger is by design ephemeral. If you need durability before v0.2's Redis backend ships, stand up an external accounting system (BigQuery/Postgres) downstream of `/metrics` and treat the governor as fast-path enforcement.
