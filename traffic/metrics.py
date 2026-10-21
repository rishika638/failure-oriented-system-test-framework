import threading
import time
from collections import Counter


class MetricsCollector:
    def __init__(self):
        self.latencies = []
        self.status_codes = Counter()
        self.errors = Counter()
        self._lock = threading.Lock()
        self.start_time = time.monotonic()

    def record(self, latency_ms, status_code=None, error=None):
        with self._lock:
            self.latencies.append(latency_ms)
            if status_code is not None:
                self.status_codes[status_code] += 1
            if error is not None:
                self.errors[error] += 1

    def record_skipped(self, count=1):
        with self._lock:
            self.errors["overloaded"] += count

    def summary(self, scheduled=None):
        elapsed = max(time.monotonic() - self.start_time, 0.000001)
        with self._lock:
            latencies = sorted(self.latencies)
            statuses = dict(sorted(self.status_codes.items()))
            errors = dict(sorted(self.errors.items()))

        def percentile(p):
            if not latencies:
                return None
            position = (len(latencies) - 1) * p / 100
            lower = int(position)
            upper = min(lower + 1, len(latencies) - 1)
            return round(latencies[lower] + (latencies[upper] - latencies[lower]) * (position - lower), 2)

        return {
            "requests": len(latencies),
            "scheduled": scheduled if scheduled is not None else len(latencies),
            "errors": sum(errors.values()),
            "error_types": errors,
            "status_codes": statuses,
            "throughput_rps": round(len(latencies) / elapsed, 2),
            "error_rate": round(sum(errors.values()) / max(scheduled or len(latencies), 1), 4),
            "timeouts": errors.get("timeout", 0),
            "non_2xx": sum(count for code, count in statuses.items() if code < 200 or code >= 300),
            "p50_ms": percentile(50),
            "p95_ms": percentile(95),
            "p99_ms": percentile(99),
            "min_ms": round(latencies[0], 2) if latencies else None,
            "max_ms": round(latencies[-1], 2) if latencies else None,
            "duration_s": round(elapsed, 3),
        }