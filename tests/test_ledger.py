from agent_cost_governor.ledger import BudgetLedger


def test_record_and_used():
    led = BudgetLedger()
    led.record("acme", 0.5)
    led.record("acme", 1.25)
    led.record("other", 9.99)
    assert round(led.used("acme"), 4) == 1.75
    assert round(led.used("other"), 4) == 9.99
    assert led.used("missing") == 0.0


def test_used_pct_handles_zero_budget():
    led = BudgetLedger()
    led.record("t", 0.5)
    assert led.used_pct("t", 0.0) == 1.0


def test_window_expires_old_spend():
    led = BudgetLedger(window_seconds=0.1)
    led.record("t", 1.0)
    import time

    time.sleep(0.15)
    assert led.used("t") == 0.0


def test_reset_clears_specific_tenant():
    led = BudgetLedger()
    led.record("a", 1.0)
    led.record("b", 2.0)
    led.reset("a")
    assert led.used("a") == 0.0
    assert led.used("b") == 2.0


def test_snapshot_returns_all_tenants():
    led = BudgetLedger()
    led.record("a", 0.10)
    led.record("b", 0.20)
    snap = led.snapshot()
    assert set(snap.keys()) == {"a", "b"}
