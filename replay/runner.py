import os
import time

import requests

from replay.environment import validated_target
from scenarios.loader import load_scenario


def run_replay(scenario_name: str, captured_path: str) -> dict:
    scenario = load_scenario(scenario_name)
    if captured_path != scenario.path:
        raise ValueError("Captured path does not match the approved scenario fixture")
    url = validated_target(scenario.path)
    headers = {"Accept": "application/json", "X-Replay-Request": "true"}
    proxy_token = os.environ.get("FAULT_PROXY_TOKEN")
    if proxy_token:
        headers["X-Fault-Proxy-Token"] = proxy_token
    if scenario.fault == "latency":
        headers["X-Engine-Fault"] = f"latency:{scenario.latency_ms}"
    elif scenario.fault == "timeout":
        headers["X-Engine-Fault"] = f"timeout:{min(scenario.timeout_ms + 250, 30_000)}"
    elif scenario.fault == "dependency":
        headers["X-Engine-Fault"] = "dependency"

    started = time.monotonic()
    try:
        response = requests.get(
            url, headers=headers, timeout=scenario.timeout_ms / 1000, allow_redirects=False
        )
        injected = {
            "status_code": response.status_code,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "outcome": "response",
        }
    except requests.Timeout:
        injected = {
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "outcome": "timeout",
        }
    except requests.RequestException:
        injected = {
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "outcome": "connection_error",
        }
    recovery_started = time.monotonic()
    recovery_headers = {"Accept": "application/json", "X-Replay-Request": "true"}
    if proxy_token:
        recovery_headers["X-Fault-Proxy-Token"] = proxy_token
    try:
        response = requests.get(
            url,
            headers=recovery_headers,
            timeout=5,
            allow_redirects=False,
        )
        recovery = {
            "status_code": response.status_code,
            "latency_ms": round((time.monotonic() - recovery_started) * 1000, 2),
            "outcome": "response",
        }
    except requests.Timeout:
        recovery = {
            "status_code": None,
            "latency_ms": round((time.monotonic() - recovery_started) * 1000, 2),
            "outcome": "timeout",
        }
    except requests.RequestException:
        recovery = {
            "status_code": None,
            "latency_ms": round((time.monotonic() - recovery_started) * 1000, 2),
            "outcome": "connection_error",
        }
    return {"injected": injected, "recovery": recovery}
