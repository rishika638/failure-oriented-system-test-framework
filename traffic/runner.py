import time
import threading
from traffic.load_generator import send_request
from traffic.metrics import MetricsCollector

def run_load(url, rps=10, duration=30, timeout=1.0):
    metrics = MetricsCollector()
    stop_event = threading.Event()

    interval = 1.0 / rps
    end_time = time.time() + duration

    def worker():
        while not stop_event.is_set():
            if time.time() >= end_time:
                stop_event.set()
                break

            send_request(url, timeout, metrics)
            time.sleep(interval)

    threads = []
    for _ in range(4):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=duration + 2)

    return metrics.summary()