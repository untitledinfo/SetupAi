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
from dataclasses import dataclass
from threading import Lock


@dataclass
class _Sample:
    timestamp: float
    latency_ms: float
    status: str  # "success" | "error"
    endpoint: str = "chat"
    tokens: int = 0


class StatsTracker:
    def __init__(self, max_samples: int = 1000):
        self._samples: deque[_Sample] = deque(maxlen=max_samples)
        self._lock = Lock()
        self._started_at = time.time()
        self._total_tokens = 0

    def record(
        self,
        latency_ms: float,
        status: str,
        endpoint: str = "chat",
        tokens: int = 0,
    ) -> None:
        with self._lock:
            self._samples.append(
                _Sample(
                    timestamp=time.time(),
                    latency_ms=latency_ms,
                    status=status,
                    endpoint=endpoint,
                    tokens=tokens,
                )
            )
            self._total_tokens += max(0, tokens)

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._samples)
            total_tokens = self._total_tokens

        total = len(samples)
        errors = sum(1 for s in samples if s.status == "error")
        successes = total - errors
        latencies = sorted(s.latency_ms for s in samples)

        def _percentile(p: float) -> float:
            if not latencies:
                return 0.0
            idx = int(len(latencies) * p)
            idx = min(idx, len(latencies) - 1)
            return round(latencies[idx], 1)

        avg_latency = sum(latencies) / total if total else 0.0

        return {
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "requests_recorded": total,
            "success_recorded": successes,
            "errors_recorded": errors,
            "error_rate_pct": round((errors / total * 100), 2) if total else 0.0,
            "avg_latency_ms": round(avg_latency, 1),
            "min_latency_ms": round(min(latencies), 1) if latencies else 0.0,
            "max_latency_ms": round(max(latencies), 1) if latencies else 0.0,
            "p50_latency_ms": _percentile(0.50),
            "p90_latency_ms": _percentile(0.90),
            "p95_latency_ms": _percentile(0.95),
            "p99_latency_ms": _percentile(0.99),
            "tokens_generated": total_tokens,
        }
