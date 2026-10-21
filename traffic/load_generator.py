import time

import requests


def send_request(url, timeout, metrics, method="GET", headers=None, payload=None):
    start = time.monotonic()
    try:
        response = requests.request(
            method, url, headers=headers, json=payload, timeout=timeout
        )
        metrics.record(
            (time.monotonic() - start) * 1000,
            status_code=response.status_code,
            error=None if 200 <= response.status_code < 300 else "http_error",
        )
    except requests.Timeout:
        metrics.record((time.monotonic() - start) * 1000, error="timeout")
    except requests.RequestException:
        metrics.record((time.monotonic() - start) * 1000, error="connection_error")