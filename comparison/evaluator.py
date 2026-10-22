from typing import Literal

from pydantic import BaseModel, ConfigDict


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    original_status: int | None
    replay_status: int | None
    original_latency_ms: float | None
    replay_latency_ms: float | None
    latency_delta_ms: float | None
    recovery_status: int | None
    recovery_latency_ms: float | None
    signature_match: bool | None
    recovered: bool
    reason: str


def compare(
    original_status: int | None,
    original_latency_ms: float | None,
    replay_status: int | None,
    replay_latency_ms: float | None,
    expected_status: int,
    recovery_status: int | None = None,
    recovery_latency_ms: float | None = None,
    recovery_max_latency_ms: float = 500.0,
    tolerance_ms: float = 100.0,
    failure_reproduced: bool | None = None,
    original_fingerprint: str | None = None,
    replay_fingerprint: str | None = None,
) -> Comparison:
    if (original_latency_ms is None or replay_latency_ms is None
            or recovery_status is None or recovery_latency_ms is None
            or failure_reproduced is None and (original_status is None or replay_status is None)):
        return Comparison(
            result="INCONCLUSIVE",
            original_status=original_status,
            replay_status=replay_status,
            original_latency_ms=original_latency_ms,
            replay_latency_ms=replay_latency_ms,
            latency_delta_ms=None,
            recovery_status=recovery_status,
            recovery_latency_ms=recovery_latency_ms,
            signature_match=None,
            recovered=False,
            reason="Required original or replay measurements are missing",
        )
    delta = replay_latency_ms - original_latency_ms
    if failure_reproduced is not None:
        reproduced = failure_reproduced
    else:
        reproduced = (
            replay_status == original_status
            and abs(delta) <= tolerance_ms
        )
    signature_match = (
        original_fingerprint == replay_fingerprint
        if original_fingerprint is not None and replay_fingerprint is not None
        else None
    )
    if signature_match is False:
        reproduced = False
    recovered = recovery_status == expected_status and recovery_latency_ms <= recovery_max_latency_ms
    passed = reproduced and recovered
    return Comparison(
        result="PASS" if passed else "FAIL",
        original_status=original_status,
        replay_status=replay_status,
        original_latency_ms=original_latency_ms,
        replay_latency_ms=replay_latency_ms,
        latency_delta_ms=round(delta, 2),
        recovery_status=recovery_status,
        recovery_latency_ms=recovery_latency_ms,
        signature_match=signature_match,
        recovered=recovered,
        reason=("Failure reproduced within tolerance and the clean recovery met its threshold"
                if passed else "Failure reproduction or clean recovery did not meet its threshold"),
    )
