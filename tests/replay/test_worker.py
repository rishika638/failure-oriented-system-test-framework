from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import worker.jobs
from incident_store.database import Base
from incident_store.models import AuditEvent, Capture, Incident, ReplayJob


def test_interrupted_replay_is_marked_failed_and_audited(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(worker.jobs, "SessionLocal", session_factory)
    with session_factory() as session:
        incident = Incident(
            id="incident-1",
            organization_id="org-1",
            fingerprint="a" * 64,
            scenario="latency",
            status="open",
        )
        capture = Capture(
            id="capture-1",
            incident_id=incident.id,
            organization_id=incident.organization_id,
            scenario="latency",
            snapshot={},
        )
        replay = ReplayJob(
            id="replay-1",
            incident_id=incident.id,
            capture_id=capture.id,
            organization_id=incident.organization_id,
            idempotency_key="interrupted-1",
            status="running",
            original_artifact={},
        )
        session.add_all([incident, capture, replay])
        session.commit()

    try:
        worker.jobs.mark_replay_failed(
            SimpleNamespace(args=("replay-1",)),
            None,
            TimeoutError,
            TimeoutError("execution timeout"),
            None,
        )

        with session_factory() as session:
            replay = session.get(ReplayJob, "replay-1")
            assert replay.status == "failed"
            assert replay.error == "Replay exceeded execution limits or the worker failed"
            event = session.query(AuditEvent).one()
            assert event.event_type == "replay.failed"
            assert event.details["error_type"] == "TimeoutError"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
