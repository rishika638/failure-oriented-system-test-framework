import pytest
from pydantic import ValidationError

from comparison.evaluator import compare
from capture.normalizer import failure_fingerprint_values
from fault_injection.policy import parse_fault
from scenarios.loader import load_scenario
from scenarios.schema import Scenario


@pytest.mark.parametrize("name", ["latency", "timeout", "dependency"])
def test_versioned_scenarios_load(name):
    scenario = load_scenario(name)
    assert scenario.schema_version == "1.0"
    assert scenario.name == name


def test_scenario_rejects_unsafe_path():
    with pytest.raises(ValidationError):
        Scenario(
            schema_version="1.0",
            name="latency",
            method="GET",
            path="//attacker.invalid/",
            fault="latency",
        )


def test_fault_policy_bounds_jitter_and_timeout():
    assert parse_fault("jitter:10:25").jitter_max_ms == 25
    assert parse_fault("timeout:30000").delay_ms == 30000
    with pytest.raises(ValueError):
        parse_fault("jitter:100:10")
    with pytest.raises(ValueError):
        parse_fault("latency:30001")


def test_comparison_requires_failure_reproduction_and_recovery():
    result = compare(503, 320, 503, 331, 200, 200, 75, 500, 100)
    assert result.result == "PASS"
    assert result.recovered is True

    failed = compare(503, 320, 200, 20, 200, 200, 20, 500, 100)
    assert failed.result == "FAIL"
    assert failed.recovered is True

    unknown = compare(503, 320, None, 100, 200, 200, 20, 500, 100)
    assert unknown.result == "INCONCLUSIVE"


def test_timeout_is_compared_by_observed_outcome_even_without_http_status():
    fingerprint = failure_fingerprint_values("timeout", "GET", "/ping", 504)
    result = compare(
        504, 100, None, 101, 200,
        recovery_status=200, recovery_latency_ms=50,
        failure_reproduced=True,
        original_fingerprint=fingerprint,
        replay_fingerprint=fingerprint,
    )
    assert result.result == "PASS"
    assert result.signature_match is True


def test_fingerprint_mismatch_fails_even_when_recovery_is_healthy():
    result = compare(
        503, 320, 503, 321, 200,
        recovery_status=200, recovery_latency_ms=50,
        failure_reproduced=True,
        original_fingerprint="original",
        replay_fingerprint="different",
    )
    assert result.result == "FAIL"
    assert result.signature_match is False
