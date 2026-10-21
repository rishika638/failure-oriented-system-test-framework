import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, Worker
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from urllib.parse import urlsplit

from api.auth import current_organization, organization_keys
from api.logging_config import configure_logging
from api.middleware import RequestSizeLimitMiddleware
from api.schemas import IncidentStatusUpdate, ReplayRequest
from capture.normalizer import create_snapshot
from capture.schema import CaptureInput
from incident_store.database import engine, get_session
from incident_store.lifecycle import transition, transition_replay
from incident_store.models import AuditEvent, Capture, Incident, ReplayJob
from replay.environment import validated_target
from worker.jobs import mark_replay_failed


configure_logging()
logger = logging.getLogger("failure_engine.api")
app = FastAPI(title="Production Failure Capture & Replay Engine", version="1.0.0")

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=256 * 1024)
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@app.middleware("http")
async def request_correlation(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")[:128] or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _incident_summary(incident, capture_count=0):
    return {
        "id": incident.id,
        "fingerprint": incident.fingerprint,
        "scenario": incident.scenario,
        "status": incident.status,
        "capture_count": capture_count,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }


def _session_dependency():
    yield from get_session()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    try:
        app_env = os.environ.get("APP_ENV", "development")
        if app_env not in {"development", "production"}:
            raise RuntimeError("APP_ENV must be development or production")
        organization_keys()
        if app_env == "production":
            required = (
                "DATABASE_URL",
                "REDIS_URL",
                "REPLAY_TARGET_URL",
                "REPLAY_ALLOWED_HOSTS",
                "FAULT_PROXY_TOKEN",
                "CORS_ORIGINS",
            )
            if any(not os.environ.get(name) for name in required):
                raise RuntimeError("Production API configuration is incomplete")
            if "*" in allowed_origins:
                raise RuntimeError("CORS_ORIGINS must use exact origins in production")
            if len(os.environ["FAULT_PROXY_TOKEN"]) < 32:
                raise RuntimeError("FAULT_PROXY_TOKEN must contain at least 32 characters")
            for origin in allowed_origins:
                parsed_origin = urlsplit(origin)
                if (
                    parsed_origin.scheme != "https"
                    or not parsed_origin.hostname
                    or parsed_origin.username
                    or parsed_origin.password
                    or parsed_origin.path not in {"", "/"}
                    or parsed_origin.query
                    or parsed_origin.fragment
                ):
                    raise RuntimeError("Production CORS_ORIGINS must contain exact HTTPS origins")
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            redis = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            redis.ping()
            if app_env == "production" and not Worker.all(connection=redis):
                raise RuntimeError("No active replay worker is registered")
        elif os.environ.get("APP_ENV") == "production":
            raise RuntimeError("REDIS_URL is required in production")
        if os.environ.get("REPLAY_TARGET_URL"):
            proxy_health = validated_target("/health")
            with httpx.Client(
                timeout=2,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.get(proxy_health)
                if response.status_code != 200:
                    raise RuntimeError("Synthetic replay proxy is not ready")
    except Exception as error:
        logger.exception("Readiness check failed")
        raise HTTPException(status_code=503, detail="A required service is unavailable") from error
    return {"status": "ready"}


@app.post("/v1/captures", status_code=201)
def ingest_capture(
    payload: CaptureInput,
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    from capture.normalizer import failure_fingerprint

    fingerprint = failure_fingerprint(payload)
    incident = session.scalar(select(Incident).where(
        Incident.organization_id == organization_id,
        Incident.fingerprint == fingerprint,
    ))
    created = False
    if incident is None:
        incident = Incident(
            organization_id=organization_id,
            fingerprint=fingerprint,
            scenario=payload.scenario,
            status="open",
        )
        session.add(incident)
        try:
            session.flush()
            created = True
        except IntegrityError:
            session.rollback()
            incident = session.scalar(select(Incident).where(
                Incident.organization_id == organization_id,
                Incident.fingerprint == fingerprint,
            ))
            if incident is None:
                raise
    else:
        incident.updated_at = datetime.now(timezone.utc)
    if created:
        session.add(AuditEvent(
            organization_id=organization_id,
            incident_id=incident.id,
            event_type="incident.created",
            details={"scenario": payload.scenario},
        ))
    capture_id = uuid.uuid4()
    snapshot = create_snapshot(payload, capture_id)
    capture = Capture(
        id=str(capture_id),
        incident_id=incident.id,
        organization_id=organization_id,
        scenario=payload.scenario,
        snapshot=snapshot.model_dump(mode="json"),
    )
    session.add(capture)
    session.add(AuditEvent(
        organization_id=organization_id,
        incident_id=incident.id,
        event_type="capture.ingested",
        details={"capture_id": str(capture_id)},
    ))
    session.commit()
    return {"capture_id": str(capture_id), "incident": _incident_summary(incident)}


@app.get("/v1/incidents")
def list_incidents(
    status: str | None = Query(default=None, pattern="^(open|investigating|resolved)$"),
    scenario: str | None = Query(default=None, pattern="^(latency|timeout|dependency)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    query = select(Incident).where(Incident.organization_id == organization_id)
    if status:
        query = query.where(Incident.status == status)
    if scenario:
        query = query.where(Incident.scenario == scenario)
    incidents = session.scalars(
        query.order_by(Incident.updated_at.desc()).offset(offset).limit(limit)
    ).all()
    summaries = []
    for incident in incidents:
        count = session.scalar(select(func.count()).select_from(Capture).where(
            Capture.organization_id == organization_id,
            Capture.incident_id == incident.id,
        ))
        summaries.append(_incident_summary(incident, count or 0))
    return {"items": summaries, "limit": limit, "offset": offset}


@app.get("/v1/incidents/{incident_id}")
def get_incident(
    incident_id: str,
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    incident = session.scalar(select(Incident).where(
        Incident.id == incident_id, Incident.organization_id == organization_id,
    ))
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    captures = session.scalars(select(Capture).where(
        Capture.incident_id == incident.id, Capture.organization_id == organization_id,
    ).order_by(Capture.created_at.desc()).limit(100)).all()
    jobs = session.scalars(select(ReplayJob).where(
        ReplayJob.incident_id == incident.id,
        ReplayJob.organization_id == organization_id,
    ).order_by(ReplayJob.created_at.desc()).limit(100)).all()
    events = session.scalars(select(AuditEvent).where(
        AuditEvent.incident_id == incident.id,
        AuditEvent.organization_id == organization_id,
    ).order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return {
        "incident": _incident_summary(incident, len(captures)),
        "captures": [{"id": capture.id, "snapshot": capture.snapshot, "created_at": capture.created_at.isoformat()} for capture in captures],
        "replays": [{
            "id": job.id,
            "capture_id": job.capture_id,
            "status": job.status,
            "original": job.original_artifact,
            "replay": job.replay_artifact,
            "comparison": job.comparison,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
        } for job in jobs],
        "history": [{
            "event_type": event.event_type,
            "details": event.details,
            "created_at": event.created_at.isoformat(),
        } for event in events],
    }


@app.patch("/v1/incidents/{incident_id}")
def update_incident(
    incident_id: str,
    update: IncidentStatusUpdate,
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    incident = session.scalar(select(Incident).where(
        Incident.id == incident_id, Incident.organization_id == organization_id,
    ).with_for_update())
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    previous = incident.status
    transition(incident, update.status)
    session.add(AuditEvent(
        organization_id=organization_id,
        incident_id=incident.id,
        event_type="incident.status_changed",
        details={"from": previous, "to": update.status},
    ))
    session.commit()
    return {"incident": _incident_summary(incident)}


@app.post("/v1/incidents/{incident_id}/replays", status_code=202)
def submit_replay(
    incident_id: str,
    request_data: ReplayRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    incident = session.scalar(select(Incident).where(
        Incident.id == incident_id, Incident.organization_id == organization_id,
    ).with_for_update())
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    existing = session.scalar(select(ReplayJob).where(
        ReplayJob.incident_id == incident_id,
        ReplayJob.organization_id == organization_id,
        ReplayJob.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        response.status_code = 200
        return {"replay_id": existing.id, "status": existing.status}
    capture = session.scalar(select(Capture).where(
        Capture.id == str(request_data.capture_id),
        Capture.incident_id == incident.id,
        Capture.organization_id == organization_id,
    ))
    if capture is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    job = ReplayJob(
        incident_id=incident.id,
        capture_id=capture.id,
        organization_id=organization_id,
        idempotency_key=idempotency_key,
        original_artifact=capture.snapshot,
    )
    session.add(job)
    session.add(AuditEvent(
        organization_id=organization_id,
        incident_id=incident.id,
        event_type="replay.queued",
        details={"capture_id": capture.id},
    ))
    session.commit()
    try:
        redis_url = os.environ["REDIS_URL"]
        queue = Queue("replays", connection=Redis.from_url(redis_url), default_timeout=60)
        queue.enqueue(
            "worker.jobs.execute_replay",
            job.id,
            job_id=f"replay-{job.id}",
            job_timeout=60,
            result_ttl=3600,
            failure_ttl=86400,
            on_failure=mark_replay_failed,
        )
    except (KeyError, RedisError, OSError) as error:
        logger.exception("Could not enqueue replay", extra={"replay_job_id": job.id})
        transition_replay(job, "failed")
        job.error = "Replay queue is unavailable"
        session.add(AuditEvent(
            organization_id=organization_id,
            incident_id=incident.id,
            event_type="replay.enqueue_failed",
            details={"job_id": job.id},
        ))
        session.commit()
        raise HTTPException(status_code=503, detail="Replay queue is unavailable") from error
    return {"replay_id": job.id, "status": job.status}


@app.get("/v1/replays/{replay_id}")
def get_replay(
    replay_id: str,
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    job = session.scalar(select(ReplayJob).where(
        ReplayJob.id == replay_id, ReplayJob.organization_id == organization_id,
    ))
    if job is None:
        raise HTTPException(status_code=404, detail="Replay not found")
    return {
        "id": job.id,
        "incident_id": job.incident_id,
        "capture_id": job.capture_id,
        "status": job.status,
        "original": job.original_artifact,
        "replay": job.replay_artifact,
        "comparison": job.comparison,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
    }


@app.get("/v1/replays/{replay_id}/comparison")
def get_comparison(
    replay_id: str,
    organization_id: str = Depends(current_organization),
    session: Session = Depends(_session_dependency),
):
    job = session.scalar(select(ReplayJob).where(
        ReplayJob.id == replay_id, ReplayJob.organization_id == organization_id,
    ))
    if job is None:
        raise HTTPException(status_code=404, detail="Replay not found")
    if job.comparison is None:
        raise HTTPException(status_code=409, detail="Comparison is not available yet")
    return job.comparison
