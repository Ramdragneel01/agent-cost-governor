"""Alerting: best-effort webhook fire-and-forget.

The alerter is intentionally simple — log + optional webhook. Production
deployments can swap ``WebhookAlerter`` for a Slack-block-formatted variant
or a queue-backed sender.
"""
from __future__ import annotations

import json
from typing import Optional, Protocol

import httpx
import structlog

log = structlog.get_logger("agent-cost-governor.alerts")


class Alerter(Protocol):
    async def fire(self, tenant: str, used_pct: float, used_usd: float, budget_usd: float) -> None:
        ...  # pragma: no cover


class NoopAlerter:
    async def fire(self, tenant: str, used_pct: float, used_usd: float, budget_usd: float) -> None:
        log.info(
            "budget_alert",
            tenant=tenant,
            used_pct=round(used_pct, 4),
            used_usd=round(used_usd, 4),
            budget_usd=budget_usd,
        )


class WebhookAlerter:
    """POST a JSON body to ``url``. Errors are swallowed; alerting must never break the proxy."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def fire(self, tenant: str, used_pct: float, used_usd: float, budget_usd: float) -> None:
        body = {
            "type": "agent-cost-governor.budget_alert",
            "tenant": tenant,
            "used_pct": round(used_pct, 4),
            "used_usd": round(used_usd, 4),
            "budget_usd": budget_usd,
            "text": (
                f":warning: tenant `{tenant}` at "
                f"{used_pct*100:.1f}% of daily budget "
                f"(${used_usd:.2f} / ${budget_usd:.2f})"
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.url, json=body)
        except Exception as exc:  # noqa: BLE001 - alerting must not crash the proxy
            log.warning("alert_webhook_failed", error=str(exc), url=self.url)


def build_alerter(webhook_url: Optional[str]) -> Alerter:
    if webhook_url:
        return WebhookAlerter(webhook_url)
    return NoopAlerter()
