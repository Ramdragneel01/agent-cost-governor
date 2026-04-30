"""FastAPI application: proxy + budget governance."""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from . import __version__
from .alerts import build_alerter
from .config import Settings, get_settings
from .ledger import BudgetLedger
from .metrics import AuditEvent, metrics
from .policy import Policy, load_policy
from .pricing import estimate_cost_usd, extract_response_usage
from .routing import decide

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def create_app(
    settings: Settings | None = None,
    policy: Policy | None = None,
    ledger: BudgetLedger | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    policy = policy or _safe_load_policy(settings.policy_path)
    ledger = ledger or BudgetLedger()
    alerter = build_alerter(settings.alert_webhook_url or None)

    app = FastAPI(
        title="agent-cost-governor",
        version=__version__,
        description="FinOps proxy: per-tenant token budgets, downgrade routing, alerts.",
    )
    app.state.settings = settings
    app.state.policy = policy
    app.state.ledger = ledger
    app.state.alerter = alerter

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        snap = metrics.snapshot()
        snap["spend_window_24h_usd"] = ledger.snapshot()
        return snap

    @app.get("/metrics")
    def prom_metrics() -> Response:
        return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")

    @app.post("/v1/proxy/{path:path}")
    async def proxy(path: str, request: Request) -> Response:
        return await _handle_proxy(path, request, app)

    return app


def _safe_load_policy(path: str) -> Policy:
    try:
        return load_policy(path)
    except FileNotFoundError:
        # Empty policy: defaults applied to everyone.
        return Policy(pricing={}, tenants={}, defaults=_default_tenant_policy())


def _default_tenant_policy():
    from .policy import TenantPolicy

    return TenantPolicy(
        name="__defaults__",
        daily_budget_usd=5.0,
        block_at_pct=1.0,
        alert_at_pct=0.8,
    )


async def _handle_proxy(path: str, request: Request, app: FastAPI) -> Response:
    settings: Settings = app.state.settings
    policy: Policy = app.state.policy
    ledger: BudgetLedger = app.state.ledger

    raw = await request.body()
    try:
        payload: dict = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_json", "message": "Body must be valid JSON."}},
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_payload", "message": "Body must be a JSON object."}},
        )

    tenant = request.headers.get(settings.tenant_header, settings.default_tenant)
    decision = decide(payload, tenant, policy, ledger)

    if not decision.allowed:
        metrics.record(
            AuditEvent(
                ts=_now(),
                tenant=tenant,
                decision="block",
                original_model=decision.original_model,
                chosen_model=decision.chosen_model,
                used_pct=decision.used_pct,
            )
        )
        if decision.alert:
            await app.state.alerter.fire(tenant, decision.used_pct, decision.used_usd, decision.budget_usd)
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": decision.blocked_reason,
                    "message": "Daily budget exhausted for this tenant.",
                    "tenant": tenant,
                    "used_usd": round(decision.used_usd, 4),
                    "budget_usd": decision.budget_usd,
                }
            },
        )

    # Apply downgrade by mutating the request body.
    if decision.downgraded:
        payload["model"] = decision.chosen_model
        raw = json.dumps(payload).encode("utf-8")

    # Forward
    upstream_url = f"{settings.upstream_base_url.rstrip('/')}/{path}"
    forward_headers = _build_forward_headers(request.headers, settings)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            upstream = await client.post(upstream_url, content=raw, headers=forward_headers)
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "upstream_error", "message": str(exc)}},
        )

    # Account exact cost from the response.
    cost_usd = 0.0
    try:
        body_json = upstream.json()
        prompt_t, comp_t = extract_response_usage(body_json)
        cost_usd = estimate_cost_usd(decision.chosen_model, prompt_t, comp_t, policy.pricing)
        ledger.record(tenant, cost_usd)
    except Exception:
        # Non-JSON responses (e.g., streaming) are not accounted in v0.1.
        pass

    metrics.record(
        AuditEvent(
            ts=_now(),
            tenant=tenant,
            decision="downgrade" if decision.downgraded else "allow",
            original_model=decision.original_model,
            chosen_model=decision.chosen_model,
            cost_usd=cost_usd,
            used_pct=ledger.used_pct(tenant, decision.budget_usd),
        )
    )

    if decision.alert:
        await app.state.alerter.fire(tenant, decision.used_pct, decision.used_usd, decision.budget_usd)

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


def _build_forward_headers(incoming, settings: Settings) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in incoming.items():
        lk = key.lower()
        if lk in _HOP_BY_HOP:
            continue
        if lk == "authorization" or lk == settings.tenant_header.lower():
            continue
        out[key] = value
    if settings.upstream_api_key:
        out["authorization"] = f"Bearer {settings.upstream_api_key}"
    out.setdefault("content-type", "application/json")
    return out


def _now() -> float:
    import time
    return time.time()


app = create_app()
