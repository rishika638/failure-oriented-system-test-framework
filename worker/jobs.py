import logging

from comparison.evaluator import compare
from capture.normalizer import failure_fingerprint_values, verify_snapshot
from capture.schema import FailureSnapshot
from incident_store.database import SessionLocal
from incident_store.lifecycle import transition_replay
from incident_store.models import AuditEvent, ReplayJob
from replay.runner import run_replay
from scenarios.loader import load_scenario


logger = logging.getLogger(__name__)


def execute_replay(job_id: str):
    with SessionLocal() as session:
        job = session.get(ReplayJob, job_id)
        if job is None or job.status != "queued":
            return
        transition_replay(job, "running")
        session.commit()
        try:
            scenario = load_scenario(job.original_artifact["scenario"])
            snapshot = FailureSnapshot.model_validate(job.original_artifact)
            if not verify_snapshot(snapshot):
                raise ValueError("Capture integrity check failed")
            original = job.original_artifact["measurements"]
            replay = run_replay(scenario.name, job.original_artifact["request"]["path"])
            injected = replay["injected"]
            original_status = original.get("status_code")
            captured_path = job.original_artifact["request"]["path"]
            replay_status = injected.get("status_code")
            signature_status = replay_status
            if signature_status is None and scenario.fault == "timeout" and injected.get("outcome") == "timeout":
                signature_status = 504
            replay_fingerprint = (
                failure_fingerprint_values(scenario.name, scenario.method, captured_path, signature_status)
                if signature_status is not None
                else None
            )
            signature_match = snapshot.fingerprint == replay_fingerprint if replay_fingerprint else False
            failure_reproduced = (
                signature_match
                and (
                    replay_status == original_status
                    if replay_status is not None
                    else scenario.fault == "timeout"
                    and injected.get("outcome") == "timeout"
                    and isinstance(original_status, int)
                    and original_status >= 500
                )
            )
            result = compare(
                original_status,
                original.get("latency_ms"),
                injected.get("status_code"),
                injected.get("latency_ms"),
                scenario.expected_status,
                recovery_status=replay["recovery"].get("status_code"),
                recovery_latency_ms=replay["recovery"].get("latency_ms"),
                recovery_max_latency_ms=scenario.recovery_max_latency_ms,
                tolerance_ms=max(100, scenario.latency_ms * 0.25),
                failure_reproduced=failure_reproduced,
                original_fingerprint=snapshot.fingerprint,
                replay_fingerprint=replay_fingerprint,
            )
            job.replay_artifact = {
                "injected": replay["injected"],
                "recovery": replay["recovery"],
            }
            job.comparison = result.model_dump()
            transition_replay(job, "completed")
            session.add(AuditEvent(
                organization_id=job.organization_id,
                incident_id=job.incident_id,
                event_type="replay.completed",
                details={"job_id": job.id, "result": result.result},
            ))
        except Exception as error:
            logger.exception("Replay job failed", extra={"replay_job_id": job_id})
            transition_replay(job, "failed")
            job.error = f"{type(error).__name__}: replay execution failed"
            session.add(AuditEvent(
                organization_id=job.organization_id,
                incident_id=job.incident_id,
                event_type="replay.failed",
                details={"job_id": job.id, "error_type": type(error).__name__},
            ))
        session.commit()


def mark_replay_failed(rq_job, _connection, exception_type, _exception_value, _traceback):
    replay_id = rq_job.args[0]
    with SessionLocal() as session:
        job = session.get(ReplayJob, replay_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        transition_replay(job, "failed")
        job.error = "Replay exceeded execution limits or the worker failed"
        session.add(AuditEvent(
            organization_id=job.organization_id,
            incident_id=job.incident_id,
            event_type="replay.failed",
            details={
                "job_id": job.id,
                "error_type": getattr(exception_type, "__name__", "WorkerFailure"),
            },
        ))
        session.commit()
