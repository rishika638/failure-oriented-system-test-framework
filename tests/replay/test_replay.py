import threading

import requests
from werkzeug.serving import make_server

import replay.runner
from replay.runner import run_replay
from target.http_service.server import create_app


def test_latency_replay_records_injected_and_clean_recovery(monkeypatch):
    monkeypatch.setenv("ENABLE_TEST_FAULTS", "true")
    server = make_server("127.0.0.1", 0, create_app(), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REPLAY_TARGET_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("REPLAY_ALLOW_PRIVATE_TARGETS", "true")
    try:
        result = run_replay("latency", "/ping")
    finally:
        server.shutdown()
        thread.join(timeout=2)
    assert result["injected"]["status_code"] == 200
    assert result["injected"]["latency_ms"] >= 300
    assert result["recovery"]["status_code"] == 200
    assert result["recovery"]["latency_ms"] < 300


def test_connection_abort_is_recorded_as_transport_evidence(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REPLAY_TARGET_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("REPLAY_ALLOW_PRIVATE_TARGETS", "true")
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"
    calls = iter([
        requests.exceptions.ChunkedEncodingError("synthetic connection abort"),
        response,
    ])
    def fake_get(*args, **kwargs):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(replay.runner.requests, "get", fake_get)

    result = run_replay("latency", "/ping")
    assert result["injected"]["status_code"] is None
    assert result["injected"]["outcome"] == "connection_error"
    assert result["recovery"]["status_code"] == 200
