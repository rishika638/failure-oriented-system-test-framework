import time
import requests

def send_request(url, timeout, metrics):
    start = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        latency_ms = int((time.time() - start) * 1000)

        if r.status_code == 200:
            metrics.record_success(latency_ms)
        else:
            metrics.record_error()

    except Exception:
        metrics.record_error()