import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from traffic.load_generator import send_request
from traffic.metrics import MetricsCollector


def run_load(url, rps=10, duration=30, timeout=1.0, concurrency=32):
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be an http or https URL")
    if not math.isfinite(rps) or rps <= 0 or rps > 1000:
        raise ValueError("rps must be greater than 0 and no more than 1000")
    if not math.isfinite(duration) or duration <= 0 or duration > 3600:
        raise ValueError("duration must be greater than 0 and no more than 3600 seconds")
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
        raise ValueError("timeout must be greater than 0 and no more than 300 seconds")
    if not isinstance(concurrency, int) or not 1 <= concurrency <= 128:
        raise ValueError("concurrency must be between 1 and 128")

    metrics = MetricsCollector()
    interval = 1.0 / rps
    start_time = time.monotonic()
    deadline = start_time + duration
    next_request = start_time
    scheduled = 0
    pending = set()
    capacity = threading.BoundedSemaphore(concurrency * 2)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while next_request < deadline:
            now = time.monotonic()
            if now < next_request:
                time.sleep(next_request - now)
                now = time.monotonic()
            missed = int(max(0, now - next_request) // interval)
            if missed:
                metrics.record_skipped(missed)
                scheduled += missed
                next_request += missed * interval
            if capacity.acquire(blocking=False):
                future = executor.submit(send_request, url, timeout, metrics)
                future.add_done_callback(lambda _future: capacity.release())
                pending.add(future)
                completed = {future for future in pending if future.done()}
                for completed_future in completed:
                    completed_future.result()
                pending.difference_update(completed)
            else:
                metrics.record_skipped()
            scheduled += 1
            next_request += interval

        for future in pending:
            future.result()

    # The executor waits for every submitted request before returning.
    return metrics.summary(scheduled=scheduled)