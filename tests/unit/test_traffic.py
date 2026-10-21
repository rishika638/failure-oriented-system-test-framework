import pytest

from traffic.metrics import MetricsCollector
from traffic.runner import run_load


def test_metrics_include_status_timeout_and_percentiles():
    metrics = MetricsCollector()
    metrics.record(10, status_code=200)
    metrics.record(20, status_code=503, error="http_error")
    metrics.record(40, error="timeout")
    result = metrics.summary(scheduled=3)

    assert result["requests"] == 3
    assert result["status_codes"] == {200: 1, 503: 1}
    assert result["timeouts"] == 1
    assert result["errors"] == 2
    assert result["p50_ms"] == 20
    assert result["p95_ms"] == 38
    assert result["throughput_rps"] > 0


def test_metrics_summarize_all_errors_without_status_codes():
    metrics = MetricsCollector()
    metrics.record(10, error="timeout")
    metrics.record(20, error="connection_error")
    metrics.record_skipped()

    result = metrics.summary(scheduled=3)

    assert result["requests"] == 2
    assert result["status_codes"] == {}
    assert result["errors"] == 3
    assert result["error_types"] == {
        "connection_error": 1,
        "overloaded": 1,
        "timeout": 1,
    }
    assert result["error_rate"] == 1
    assert result["timeouts"] == 1
    assert result["p50_ms"] == 15


def test_scheduler_uses_one_fixed_rate_schedule(monkeypatch):
    calls = []

    def fake_request(_url, _timeout, metrics):
        calls.append(1)
        metrics.record(2, status_code=200)

    monkeypatch.setattr("traffic.runner.send_request", fake_request)
    result = run_load("http://example.test/ping", rps=20, duration=0.21, concurrency=2)
    assert result["scheduled"] == 5
    assert len(calls) == 5
    assert result["errors"] == 0


@pytest.mark.parametrize("args", [
    {"rps": 0},
    {"rps": 1001},
    {"duration": 3601},
    {"timeout": 0},
    {"concurrency": 129},
])
def test_scheduler_rejects_unsafe_bounds(args):
    options = {"duration": 0.1}
    options.update(args)
    with pytest.raises(ValueError):
        run_load("http://example.test", **options)
