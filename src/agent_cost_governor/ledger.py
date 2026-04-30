"""Budget ledger: tracks per-tenant spend in a rolling 24h window.

In-memory only for v0.1. The ``Ledger`` interface is a thin protocol so a
Redis-backed variant can drop in for v0.2 without touching the proxy.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple


@dataclass
class Spend:
    ts: float
    cost_usd: float


class BudgetLedger:
    """Sliding 24h window of (timestamp, cost_usd) per tenant."""

    def __init__(self, window_seconds: float = 86400.0) -> None:
        self.window = window_seconds
        self._lock = threading.Lock()
        self._spend: Dict[str, Deque[Spend]] = {}

    def _trim(self, q: Deque[Spend], now: float) -> None:
        cutoff = now - self.window
        while q and q[0].ts < cutoff:
            q.popleft()

    def record(self, tenant: str, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        now = time.time()
        with self._lock:
            q = self._spend.setdefault(tenant, deque())
            q.append(Spend(ts=now, cost_usd=cost_usd))
            self._trim(q, now)

    def used(self, tenant: str) -> float:
        now = time.time()
        with self._lock:
            q = self._spend.get(tenant)
            if not q:
                return 0.0
            self._trim(q, now)
            return sum(s.cost_usd for s in q)

    def used_pct(self, tenant: str, budget_usd: float) -> float:
        if budget_usd <= 0:
            return 1.0
        return self.used(tenant) / budget_usd

    def reset(self, tenant: str | None = None) -> None:
        with self._lock:
            if tenant is None:
                self._spend.clear()
            else:
                self._spend.pop(tenant, None)

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            now = time.time()
            out: Dict[str, float] = {}
            for tenant, q in self._spend.items():
                self._trim(q, now)
                out[tenant] = round(sum(s.cost_usd for s in q), 6)
            return out
