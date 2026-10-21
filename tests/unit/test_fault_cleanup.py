from types import SimpleNamespace

import pytest

import experiments.run_latency
import failures.latency


def test_netem_cleanup_recognizes_kernel_decimal_delay(monkeypatch):
    monkeypatch.setattr(failures.latency.platform, "system", lambda: "Linux")
    monkeypatch.setattr(failures.latency, "_active_fault", None)
    installed = False

    def fake_tc(*args):
        nonlocal installed
        if args[0:2] == ("qdisc", "show"):
            output = (
                "qdisc netem 8001: root refcnt 2 limit 1000 delay 300.0ms\n"
                if installed
                else "qdisc noqueue 0:\n"
            )
            return SimpleNamespace(stdout=output)
        if args[0:2] == ("qdisc", "add"):
            installed = True
        elif args[0:2] == ("qdisc", "del"):
            installed = False
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(failures.latency, "_run_tc", fake_tc)

    failures.latency.add_latency(300, interface="eth0")
    assert failures.latency.remove_latency()
    assert not installed
    assert failures.latency._active_fault is None


def test_latency_experiment_removes_fault_when_traffic_raises(monkeypatch):
    calls = []
    results = iter([{"p95_ms": 10}, RuntimeError("load failed")])

    def fake_run_load(*_args):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(experiments.run_latency, "run_load", fake_run_load)
    monkeypatch.setattr(
        experiments.run_latency,
        "add_latency",
        lambda *_args, **_kwargs: calls.append("add"),
    )
    monkeypatch.setattr(
        experiments.run_latency,
        "remove_latency",
        lambda: calls.append("remove"),
    )
    args = SimpleNamespace(
        url="http://synthetic.example.test/ping",
        rps=1,
        duration=1,
        timeout=1,
        concurrency=1,
        interface="eth0",
        netem_delay_ms=300,
    )

    with pytest.raises(RuntimeError, match="load failed"):
        experiments.run_latency._run(args)

    assert calls == ["add", "remove"]
