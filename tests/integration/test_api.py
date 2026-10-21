import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app, _session_dependency
from incident_store.database import Base


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({"org-a": "key-a", "org-b": "key-b"}))
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_session():
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[_session_dependency] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _capture_payload():
    return {
        "scenario": "latency",
        "method": "GET",
        "path": "/ping",
        "status_code": 200,
        "latency_ms": 380.4,
        "request_id": "request-1",
        "headers": {"authorization": "Bearer never-store-me"},
        "body": {"token": "never-store-me"},
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }


def test_capture_and_incident_are_organization_scoped(client, monkeypatch):
    monkeypatch.setenv("CAPTURE_BODY_ENABLED", "true")
    created = client.post("/v1/captures", headers={"Authorization": "Bearer key-a"}, json=_capture_payload())
    assert created.status_code == 201
    capture_id = created.json()["capture_id"]
    incident_id = created.json()["incident"]["id"]

    details = client.get(f"/v1/incidents/{incident_id}", headers={"Authorization": "Bearer key-a"})
    assert details.status_code == 200
    snapshot = details.json()["captures"][0]["snapshot"]
    assert snapshot["request"]["headers"]["authorization"] == "[REDACTED]"
    assert snapshot["request"]["body"]["token"] == "[REDACTED]"
    assert snapshot["measurements"]["latency_ms"] == 380.4

    hidden = client.get(f"/v1/incidents/{incident_id}", headers={"Authorization": "Bearer key-b"})
    assert hidden.status_code == 404
    assert capture_id == details.json()["captures"][0]["id"]


def test_authentication_and_invalid_lifecycle_transition(client):
    assert client.get("/v1/incidents").status_code == 401
    created = client.post("/v1/captures", headers={"Authorization": "Bearer key-a"}, json=_capture_payload())
    incident_id = created.json()["incident"]["id"]
    invalid = client.patch(
        f"/v1/incidents/{incident_id}",
        headers={"Authorization": "Bearer key-a"},
        json={"status": "closed"},
    )
    assert invalid.status_code == 422


def test_api_rejects_oversized_capture_body(client):
    response = client.post(
        "/v1/captures",
        headers={"Authorization": "Bearer key-a"},
        content=b"x" * (256 * 1024 + 1),
    )
    assert response.status_code == 413


def test_replay_submission_is_idempotent_and_enqueues_once(client, monkeypatch):
    enqueue_calls = []

    class FakeQueue:
        def __init__(self, *_args, **_kwargs):
            pass

        def enqueue(self, *args, **kwargs):
            enqueue_calls.append((args, kwargs))

    monkeypatch.setattr("api.main.Redis.from_url", lambda _url: object())
    monkeypatch.setattr("api.main.Queue", FakeQueue)
    monkeypatch.setenv("REDIS_URL", "redis://test.invalid/0")
    headers = {"Authorization": "Bearer key-a"}
    created = client.post("/v1/captures", headers=headers, json=_capture_payload())
    incident_id = created.json()["incident"]["id"]
    capture_id = created.json()["capture_id"]
    replay_headers = {**headers, "Idempotency-Key": "duplicate-submission-1"}
    payload = {"capture_id": capture_id}

    first = client.post(
        f"/v1/incidents/{incident_id}/replays",
        headers=replay_headers,
        json=payload,
    )
    duplicate = client.post(
        f"/v1/incidents/{incident_id}/replays",
        headers=replay_headers,
        json=payload,
    )

    assert first.status_code == 202
    assert duplicate.status_code == 200
    assert duplicate.json()["replay_id"] == first.json()["replay_id"]
    assert len(enqueue_calls) == 1
    hidden = client.get(
        f"/v1/replays/{first.json()['replay_id']}",
        headers={"Authorization": "Bearer key-b"},
    )
    assert hidden.status_code == 404


def test_other_tenant_cannot_queue_replay_for_incident_or_capture(client):
    created = client.post(
        "/v1/captures",
        headers={"Authorization": "Bearer key-a"},
        json=_capture_payload(),
    )
    incident_id = created.json()["incident"]["id"]
    response = client.post(
        f"/v1/incidents/{incident_id}/replays",
        headers={
            "Authorization": "Bearer key-b",
            "Idempotency-Key": "cross-tenant-replay-1",
        },
        json={"capture_id": created.json()["capture_id"]},
    )

    assert response.status_code == 404


def test_cors_allows_configured_dashboard_origin_only(client):
    allowed = client.options(
        "/v1/incidents",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    denied = client.options(
        "/v1/incidents",
        headers={
            "Origin": "https://unapproved.example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_production_readiness_rejects_missing_authentication_configuration(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("API_KEYS_JSON", raising=False)

    response = client.get("/ready")

    assert response.status_code == 503


def test_production_readiness_requires_a_live_worker(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({"org-a": "a" * 40}))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "redis://redis.example.test/0")
    monkeypatch.setenv("REPLAY_TARGET_URL", "https://proxy.example.test")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "proxy.example.test")
    monkeypatch.setenv("FAULT_PROXY_TOKEN", "t" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "https://dashboard.example.test")
    monkeypatch.setattr("api.main.Redis.from_url", lambda *_args, **_kwargs: type(
        "RedisStub", (), {"ping": lambda _self: True}
    )())
    monkeypatch.setattr("api.main.Worker.all", lambda **_kwargs: [])

    response = client.get("/ready")

    assert response.status_code == 503
