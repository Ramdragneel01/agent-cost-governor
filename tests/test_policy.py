from pathlib import Path

from agent_cost_governor.policy import (
    DowngradeRule,
    load_policy,
    pick_downgrade,
    policy_for_tenant,
)


def _write_policy(tmp_path: Path) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(
        """
pricing:
  gpt-4o:      { input_per_1k: 0.005,   output_per_1k: 0.015 }
  gpt-4o-mini: { input_per_1k: 0.00015, output_per_1k: 0.0006 }

defaults:
  daily_budget_usd: 5.0
  block_at_pct: 1.0
  alert_at_pct: 0.8

tenants:
  acme:
    daily_budget_usd: 50
    alert_at_pct: 0.7
    downgrade:
      - { from: gpt-4o, to: gpt-4o-mini, when: budget_pct >= 0.8 }
""",
        encoding="utf-8",
    )
    return p


def test_load_policy_parses_pricing_and_tenants(tmp_path):
    policy = load_policy(_write_policy(tmp_path))
    assert "gpt-4o" in policy.pricing
    assert policy.pricing["gpt-4o"].input_per_1k == 0.005
    acme = policy.tenants["acme"]
    assert acme.daily_budget_usd == 50
    assert acme.alert_at_pct == 0.7
    assert len(acme.downgrade) == 1
    assert acme.downgrade[0].threshold_pct == 0.8


def test_policy_for_tenant_falls_back_to_defaults(tmp_path):
    policy = load_policy(_write_policy(tmp_path))
    tp = policy_for_tenant(policy, "unknown-tenant")
    assert tp.daily_budget_usd == 5.0
    assert tp.alert_at_pct == 0.8


def test_pick_downgrade_fires_on_threshold():
    rules = [
        DowngradeRule(from_model="gpt-4o", to_model="gpt-4o-mini", threshold_pct=0.8),
    ]
    assert pick_downgrade(rules, "gpt-4o", used_pct=0.5) is None
    assert pick_downgrade(rules, "gpt-4o", used_pct=0.8) == "gpt-4o-mini"
    assert pick_downgrade(rules, "gpt-4o", used_pct=0.9) == "gpt-4o-mini"
    # Different model is unaffected
    assert pick_downgrade(rules, "claude-3.5", used_pct=0.99) is None


def test_pick_downgrade_highest_threshold_wins():
    rules = [
        DowngradeRule(from_model="gpt-4o", to_model="mid", threshold_pct=0.5),
        DowngradeRule(from_model="gpt-4o", to_model="cheap", threshold_pct=0.9),
    ]
    assert pick_downgrade(rules, "gpt-4o", used_pct=0.95) == "cheap"
    assert pick_downgrade(rules, "gpt-4o", used_pct=0.6) == "mid"
