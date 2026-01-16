import time
from collections import defaultdict

class MetricsCollector:
    def __init__(self):
        self.latencies = []
        self.errors = 0
        self.start_time = time.time()

    def record_success(self, latency_ms):
        self.latencies.append(latency_ms)

    def record_error(self):
        self.errors += 1

    def summary(self):
        if not self.latencies:
            return {}

        sorted_lat = sorted(self.latencies)

        def percentile(p):
            idx = int(len(sorted_lat) * p / 100)
            return sorted_lat[min(idx, len(sorted_lat) - 1)]

        return {
            "requests": len(self.latencies) + self.errors,
            "errors": self.errors,
            "p50_ms": percentile(50),
            "p95_ms": percentile(95),
            "p99_ms": percentile(99),
            "duration_s": int(time.time() - self.start_time),
        }