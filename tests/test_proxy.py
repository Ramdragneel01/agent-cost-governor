"""End-to-end tests of the FastAPI proxy with mocked upstream."""
from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from agent_cost_governor.app import create_app
from agent_cost_governor.config import Settings
from agent_cost_governor.ledger import BudgetLedger
from agent_cost_governor.policy import DowngradeRule, Policy, TenantPolicy
from agent_cost_governor.pricing import ModelPrice


def _settings(**overrides) -> Settings:
    base = dict(
        upstream_base_url="https://upstream.test",
        upstream_api_key="test-key",
        tenant_header="x-acg-tenant",
        default_tenant="default",
    )
    base.update(overrides)
    return Settings(**base)


def _policy() -> Policy:
    pricing = {
        "gpt-4o": ModelPrice(input_per_1k=0.005, output_per_1k=0.015),
        "gpt-4o-mini": ModelPrice(input_per_1k=0.00015, output_per_1k=0.0006),
    }
    acme = TenantPolicy(
        name="acme",
        daily_budget_usd=1.0,
        block_at_pct=1.0,
        alert_at_pct=0.8,
        downgrade=[DowngradeRule(from_model="gpt-4o", to_model="gpt-4o-mini", threshold_pct=0.8)],
    )
    defaults = TenantPolicy(name="__defaults__", daily_budget_usd=10.0)
    return Policy(pricing=pricing, tenants={"acme": acme}, defaults=defaults)


def test_health():
    client = TestClient(create_app(_settings(), _policy(), BudgetLedger()))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics_endpoint():
    client = TestClient(create_app(_settings(), _policy(), BudgetLedger()))
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "acg_decisions_total" in r.text


def test_proxy_forwards_clean_request_and_records_cost(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self._json = {
                "id": "x",
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
            }
            self.content = json.dumps(self._json).encode("utf-8")
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._json

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, content=None, headers=None):
            captured["url"] = url
            captured["body"] = json.loads(content)
            captured["auth"] = headers.get("authorization")
            return FakeResponse()

    monkeypatch.setattr("agent_cost_governor.app.httpx.AsyncClient", FakeClient)

    ledger = BudgetLedger()
    client = TestClient(create_app(_settings(), _policy(), ledger))
    r = client.post(
        "/v1/proxy/v1/chat/completions",
        headers={"x-acg-tenant": "acme"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    # gpt-4o, 1k+1k tokens = $0.005 + $0.015 = $0.020
    assert round(ledger.used("acme"), 4) == 0.0200
    assert captured["body"]["model"] == "gpt-4o"
    assert captured["auth"] == "Bearer test-key"


def test_proxy_downgrades_when_over_threshold(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        content = b'{"usage":{"prompt_tokens":0,"completion_tokens":0}}'
        headers = {"content-type": "application/json"}
        def json(self): return {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, content=None, headers=None):
            captured["body"] = json.loads(content)
            return FakeResponse()

    monkeypatch.setattr("agent_cost_governor.app.httpx.AsyncClient", FakeClient)

    ledger = BudgetLedger()
    ledger.record("acme", 0.85)  # 85% of $1.00 budget → over 0.8 threshold
    client = TestClient(create_app(_settings(), _policy(), ledger))
    r = client.post(
        "/v1/proxy/v1/chat/completions",
        headers={"x-acg-tenant": "acme"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    assert captured["body"]["model"] == "gpt-4o-mini"   # downgraded


def test_proxy_blocks_when_budget_exhausted():
    ledger = BudgetLedger()
    ledger.record("acme", 1.0)  # 100% of $1.00 budget
    client = TestClient(create_app(_settings(), _policy(), ledger))
    r = client.post(
        "/v1/proxy/v1/chat/completions",
        headers={"x-acg-tenant": "acme"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "daily_budget_exhausted"


def test_invalid_json_returns_400():
    client = TestClient(create_app(_settings(), _policy(), BudgetLedger()))
    r = client.post(
        "/v1/proxy/v1/chat/completions",
        data="not-json",
        headers={"content-type": "application/json", "x-acg-tenant": "acme"},
    )
    assert r.status_code == 400


def test_upstream_error_returns_502(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("agent_cost_governor.app.httpx.AsyncClient", FakeClient)
    client = TestClient(create_app(_settings(), _policy(), BudgetLedger()))
    r = client.post(
        "/v1/proxy/v1/chat/completions",
        headers={"x-acg-tenant": "acme"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 502


def test_default_tenant_used_when_header_missing(monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b'{"usage":{"prompt_tokens":0,"completion_tokens":0}}'
        headers = {"content-type": "application/json"}
        def json(self): return {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            return FakeResponse()

    monkeypatch.setattr("agent_cost_governor.app.httpx.AsyncClient", FakeClient)
    client = TestClient(create_app(_settings(), _policy(), BudgetLedger()))
    r = client.post(
        "/v1/proxy/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200  # falls back to "default" tenant via defaults policy
