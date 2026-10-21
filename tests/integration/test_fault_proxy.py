import threading
import time

from fastapi.testclient import TestClient
import pytest
import requests
import uvicorn
from werkzeug.serving import make_server

from fault_injection.proxy import app as proxy_app
from target.http_service.server import create_app


def test_synthetic_proxy_requires_token_and_applies_measured_delay(monkeypatch):
    monkeypatch.setenv("ENABLE_TEST_FAULTS", "true")
    upstream = make_server("127.0.0.1", 0, create_app(), threaded=True)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REPLAY_ALLOW_PRIVATE_TARGETS", "true")
    monkeypatch.setenv("FAULT_UPSTREAM_URL", f"http://127.0.0.1:{upstream.server_port}")
    monkeypatch.setenv("FAULT_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FAULT_PROXY_TOKEN", "test-only-fault-proxy-token")
    try:
        with TestClient(proxy_app) as client:
            unauthorized = client.get("/ping")
            assert unauthorized.status_code == 401
            started = time.monotonic()
            response = client.get(
                "/ping",
                headers={
                    "X-Fault-Proxy-Token": "test-only-fault-proxy-token",
                    "X-Engine-Fault": "latency:25",
                },
            )
            assert response.status_code == 200
            assert response.json()["message"] == "pong"
            assert time.monotonic() - started >= 0.07
    finally:
        upstream.shutdown()
        thread.join(timeout=2)


def test_application_connection_abort_closes_real_http_response(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REPLAY_ALLOW_PRIVATE_TARGETS", "true")
    monkeypatch.setenv("FAULT_UPSTREAM_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("FAULT_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FAULT_PROXY_TOKEN", "test-only-fault-proxy-token")
    server = uvicorn.Server(uvicorn.Config(proxy_app, host="127.0.0.1", port=0, log_level="critical"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    port = server.servers[0].sockets[0].getsockname()[1]
    session = requests.Session()
    session.trust_env = False
    try:
        with pytest.raises(requests.RequestException):
            session.get(
                f"http://127.0.0.1:{port}/ping",
                headers={
                    "X-Fault-Proxy-Token": "test-only-fault-proxy-token",
                    "X-Engine-Fault": "abort",
                },
                timeout=3,
            )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        session.close()
    assert not thread.is_alive()
