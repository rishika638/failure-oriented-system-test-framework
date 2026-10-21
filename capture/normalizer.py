import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import UUID

from capture.redaction import redact
from capture.schema import CaptureInput, FailureSnapshot


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def failure_fingerprint(capture: CaptureInput) -> str:
    return failure_fingerprint_values(
        capture.scenario,
        capture.method,
        capture.path,
        capture.status_code,
    )


def failure_fingerprint_values(scenario: str, method: str, path: str, status_code: int) -> str:
    signature = {
        "scenario": scenario,
        "method": method,
        "path": path,
        "status_class": status_code // 100,
    }
    return hashlib.sha256(_canonical(signature).encode()).hexdigest()


def create_snapshot(capture: CaptureInput, capture_id: UUID) -> FailureSnapshot:
    request = redact({
        "method": capture.method,
        "path": capture.path,
        "headers": capture.headers,
        "body": capture.body if os.environ.get("CAPTURE_BODY_ENABLED") == "true" else None,
        "request_id": capture.request_id,
    })
    measurements = {
        "status_code": capture.status_code,
        "latency_ms": capture.latency_ms,
        "observed_at": capture.occurred_at.astimezone(timezone.utc).isoformat(),
    }
    payload = {
        "schema_version": "1.0",
        "capture_id": str(capture_id),
        "scenario": capture.scenario,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "request": request,
        "measurements": measurements,
        "fingerprint": failure_fingerprint(capture),
    }
    snapshot = FailureSnapshot.model_validate({**payload, "checksum": "0" * 64})
    normalized = snapshot.model_dump(mode="json", exclude={"checksum"})
    checksum = hashlib.sha256(_canonical(normalized).encode()).hexdigest()
    return snapshot.model_copy(update={"checksum": checksum})


def verify_snapshot(snapshot: FailureSnapshot) -> bool:
    payload = snapshot.model_dump(mode="json", exclude={"checksum"})
    actual = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return actual == snapshot.checksum
