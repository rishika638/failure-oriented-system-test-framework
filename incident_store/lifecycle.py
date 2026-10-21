from fastapi import HTTPException


TRANSITIONS = {
    "open": {"investigating", "resolved"},
    "investigating": {"open", "resolved"},
    "resolved": {"open"},
}
REPLAY_TRANSITIONS = {
    "queued": {"running", "failed"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


def transition(incident, new_status):
    if new_status not in TRANSITIONS.get(incident.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid incident transition: {incident.status} -> {new_status}")
    incident.status = new_status


def transition_replay(replay, new_status):
    if new_status not in REPLAY_TRANSITIONS.get(replay.status, set()):
        raise RuntimeError(f"Invalid replay transition: {replay.status} -> {new_status}")
    replay.status = new_status
