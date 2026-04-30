"""Routing decision: combines policy, ledger, and request payload.

Pure-function, fully unit-testable without HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ledger import BudgetLedger
from .policy import Policy, pick_downgrade, policy_for_tenant
from .pricing import extract_request_tokens


@dataclass
class RoutingDecision:
    allowed: bool
    chosen_model: str
    original_model: str
    used_usd: float
    used_pct: float
    budget_usd: float
    downgraded: bool = False
    blocked_reason: str = ""
    alert: bool = False


def decide(
    payload: dict,
    tenant: str,
    policy: Policy,
    ledger: BudgetLedger,
) -> RoutingDecision:
    """Decide whether to allow, downgrade, or block a request."""
    original = str(payload.get("model", ""))
    tp = policy_for_tenant(policy, tenant)
    used = ledger.used(tenant)
    used_pct = used / tp.daily_budget_usd if tp.daily_budget_usd > 0 else 1.0

    # Hard block at 100% (or whatever the policy says)
    if used_pct >= tp.block_at_pct:
        return RoutingDecision(
            allowed=False,
            chosen_model=original,
            original_model=original,
            used_usd=used,
            used_pct=used_pct,
            budget_usd=tp.daily_budget_usd,
            blocked_reason="daily_budget_exhausted",
            alert=True,
        )

    chosen = pick_downgrade(tp.downgrade, original, used_pct) or original
    downgraded = chosen != original
    alert = used_pct >= tp.alert_at_pct

    return RoutingDecision(
        allowed=True,
        chosen_model=chosen,
        original_model=original,
        used_usd=used,
        used_pct=used_pct,
        budget_usd=tp.daily_budget_usd,
        downgraded=downgraded,
        alert=alert,
    )
