"""In-memory metrics + audit ring buffer."""
from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Deque, Dict, List


@dataclass
class AuditEvent:
    ts: float
    tenant: str
    decision: str          # "allow" | "downgrade" | "block"
    original_model: str
    chosen_model: str
    cost_usd: float = 0.0
    used_pct: float = 0.0


class MetricsStore:
    def __init__(self, audit_capacity: int = 500) -> None:
        self._lock = threading.Lock()
        self._counts: Counter[str] = Counter()
        self._cost_by_tenant: Counter[str] = Counter()
        self._audit: Deque[AuditEvent] = deque(maxlen=audit_capacity)
        self._started_at = time.time()

    def record(self, event: AuditEvent) -> None:
        with self._lock:
            self._counts[f"{event.decision}"] += 1
            if event.cost_usd:
                self._cost_by_tenant[event.tenant] += event.cost_usd
            self._audit.append(event)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self._started_at, 2),
                "decisions": dict(self._counts),
                "cost_by_tenant_usd": {k: round(v, 4) for k, v in self._cost_by_tenant.items()},
                "recent": [asdict(e) for e in list(self._audit)[-50:]],
            }

    def prometheus(self) -> str:
        with self._lock:
            lines: List[str] = [
                "# HELP acg_decisions_total Routing decisions by outcome.",
                "# TYPE acg_decisions_total counter",
            ]
            for decision, value in self._counts.items():
                lines.append(f'acg_decisions_total{{decision="{decision}"}} {value}')
            lines.append("# HELP acg_cost_usd_total Cumulative cost per tenant in USD.")
            lines.append("# TYPE acg_cost_usd_total counter")
            for tenant, value in self._cost_by_tenant.items():
                lines.append(f'acg_cost_usd_total{{tenant="{tenant}"}} {value:.6f}')
            return "\n".join(lines) + "\n"


metrics = MetricsStore()
