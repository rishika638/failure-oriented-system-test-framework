from datetime import datetime, timezone
from uuid import uuid4

from capture.normalizer import create_snapshot, verify_snapshot
from capture.schema import CaptureInput


def test_snapshot_is_redacted_versioned_and_integrity_checked(monkeypatch):
    monkeypatch.setenv("CAPTURE_BODY_ENABLED", "true")
    capture = CaptureInput(
        scenario="latency",
        method="GET",
        path="/ping",
        status_code=200,
        latency_ms=357.25,
        request_id="request-123",
        headers={"authorization": "Bearer very-secret", "user-agent": "test"},
        body={"password": "hidden", "nested": {"ok": True}},
        occurred_at=datetime.now(timezone.utc),
    )
    snapshot = create_snapshot(capture, uuid4())
    assert snapshot.schema_version == "1.0"
    assert snapshot.request["headers"]["authorization"] == "[REDACTED]"
    assert snapshot.request["body"]["password"] == "[REDACTED]"
    assert snapshot.measurements["latency_ms"] == 357.25
    assert verify_snapshot(snapshot)

    snapshot.measurements["latency_ms"] = 1
    assert not verify_snapshot(snapshot)


def test_request_body_is_not_stored_by_default(monkeypatch):
    monkeypatch.delenv("CAPTURE_BODY_ENABLED", raising=False)
    capture = CaptureInput(
        scenario="latency",
        method="GET",
        path="/ping",
        status_code=200,
        latency_ms=20,
        request_id="request-1",
        body={"private": "not stored"},
        occurred_at=datetime.now(timezone.utc),
    )
    snapshot = create_snapshot(capture, uuid4())
    assert snapshot.request["body"] is None


def test_capture_rejects_path_traversal():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CaptureInput(
            scenario="latency",
            method="GET",
            path="/safe/../secret",
            status_code=200,
            latency_ms=20,
            request_id="request-1",
            occurred_at=datetime.now(timezone.utc),
        )


def test_capture_rejects_non_finite_latency():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CaptureInput(
            scenario="latency",
            method="GET",
            path="/ping",
            status_code=200,
            latency_ms=float("nan"),
            request_id="request-1",
            occurred_at=datetime.now(timezone.utc),
        )


def test_snapshot_schema_rejects_malformed_version_and_checksum():
    import pytest
    from pydantic import ValidationError

    capture = CaptureInput(
        scenario="latency",
        method="GET",
        path="/ping",
        status_code=200,
        latency_ms=20,
        request_id="request-1",
        occurred_at=datetime.now(timezone.utc),
    )
    snapshot = create_snapshot(capture, uuid4()).model_dump(mode="json")

    snapshot["schema_version"] = "99.0"
    with pytest.raises(ValidationError):
        type(create_snapshot(capture, uuid4())).model_validate(snapshot)

    snapshot = create_snapshot(capture, uuid4()).model_dump(mode="json")
    snapshot["checksum"] = "invalid"
    with pytest.raises(ValidationError):
        type(create_snapshot(capture, uuid4())).model_validate(snapshot)
