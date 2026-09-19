"""In-memory request statistics.

Same scope caveat as the rate limiter: per-process, resets on restart,
doesn't aggregate across multiple replicas. Good enough for a
single-instance beta dashboard; swap for a real metrics backend
(Prometheus, etc.) before running multiple replicas — see
docs/troubleshooting.md.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _Sample:
    timestamp: float
    latency_ms: float
    status: str  # "success" | "error"


class StatsTracker:
    def __init__(self, max_samples: int = 1000):
        self._samples: deque[_Sample] = deque(maxlen=max_samples)
        self._lock = Lock()
        self._started_at = time.time()

    def record(self, latency_ms: float, status: str) -> None:
        with self._lock:
            self._samples.append(_Sample(time.time(), latency_ms, status))

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._samples)

        total = len(samples)
        errors = sum(1 for s in samples if s.status == "error")
        avg_latency = sum(s.latency_ms for s in samples) / total if total else 0.0

        return {
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "requests_recorded": total,
            "errors_recorded": errors,
            "avg_latency_ms": round(avg_latency, 1),
        }
