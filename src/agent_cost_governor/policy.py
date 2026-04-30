"""Policy: budgets, downgrade rules, and model pricing — declarative YAML.

Example:

    pricing:
      gpt-4o:        { input_per_1k: 0.005,  output_per_1k: 0.015 }
      gpt-4o-mini:   { input_per_1k: 0.00015, output_per_1k: 0.0006 }

    tenants:
      default:
        daily_budget_usd: 25.00
        downgrade:
          - { from: gpt-4o, to: gpt-4o-mini, when: budget_pct >= 0.8 }
        block_at_pct: 1.0   # hard-stop at 100% of budget
        alert_at_pct: 0.8

    defaults:
      daily_budget_usd: 5.00
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .pricing import ModelPrice


@dataclass
class DowngradeRule:
    from_model: str
    to_model: str
    threshold_pct: float  # 0.0..1.0


@dataclass
class TenantPolicy:
    name: str
    daily_budget_usd: float
    block_at_pct: float = 1.0
    alert_at_pct: float = 0.8
    downgrade: List[DowngradeRule] = field(default_factory=list)


@dataclass
class Policy:
    pricing: Dict[str, ModelPrice]
    tenants: Dict[str, TenantPolicy]
    defaults: TenantPolicy


def _parse_rule(item: dict) -> DowngradeRule:
    when = str(item.get("when", "")).replace(" ", "")
    threshold = 1.0
    if when.startswith("budget_pct>="):
        threshold = float(when.split(">=", 1)[1])
    elif when.startswith("budget_pct>"):
        threshold = float(when.split(">", 1)[1])
    return DowngradeRule(
        from_model=str(item["from"]),
        to_model=str(item["to"]),
        threshold_pct=threshold,
    )


def _parse_tenant(name: str, raw: dict, defaults: TenantPolicy) -> TenantPolicy:
    return TenantPolicy(
        name=name,
        daily_budget_usd=float(raw.get("daily_budget_usd", defaults.daily_budget_usd)),
        block_at_pct=float(raw.get("block_at_pct", defaults.block_at_pct)),
        alert_at_pct=float(raw.get("alert_at_pct", defaults.alert_at_pct)),
        downgrade=[_parse_rule(r) for r in raw.get("downgrade", [])],
    )


def load_policy(path: str | Path) -> Policy:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Policy file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    raw_pricing = data.get("pricing", {}) or {}
    pricing: Dict[str, ModelPrice] = {}
    for model, row in raw_pricing.items():
        pricing[str(model)] = ModelPrice(
            input_per_1k=float(row["input_per_1k"]),
            output_per_1k=float(row["output_per_1k"]),
        )

    raw_defaults = data.get("defaults", {}) or {}
    defaults = TenantPolicy(
        name="__defaults__",
        daily_budget_usd=float(raw_defaults.get("daily_budget_usd", 5.0)),
        block_at_pct=float(raw_defaults.get("block_at_pct", 1.0)),
        alert_at_pct=float(raw_defaults.get("alert_at_pct", 0.8)),
    )

    tenants: Dict[str, TenantPolicy] = {}
    for name, row in (data.get("tenants", {}) or {}).items():
        tenants[str(name)] = _parse_tenant(str(name), row or {}, defaults)

    return Policy(pricing=pricing, tenants=tenants, defaults=defaults)


def policy_for_tenant(policy: Policy, tenant: str) -> TenantPolicy:
    if tenant in policy.tenants:
        return policy.tenants[tenant]
    return TenantPolicy(
        name=tenant,
        daily_budget_usd=policy.defaults.daily_budget_usd,
        block_at_pct=policy.defaults.block_at_pct,
        alert_at_pct=policy.defaults.alert_at_pct,
    )


def pick_downgrade(rules: List[DowngradeRule], current_model: str, used_pct: float) -> Optional[str]:
    """Return the target model if a rule fires, else None.

    Highest-threshold matching rule wins (deterministic ordering).
    """
    candidates = [r for r in rules if r.from_model == current_model and used_pct >= r.threshold_pct]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.threshold_pct, reverse=True)
    return candidates[0].to_model
