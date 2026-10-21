import os

from api.logging_config import configure_logging
from redis import Redis
from rq import Queue, Worker


def validate_environment():
    app_env = os.environ.get("APP_ENV", "development")
    if app_env not in {"development", "production"}:
        raise ValueError("APP_ENV must be development or production")
    required = ["REDIS_URL"]
    if app_env == "production":
        required.extend([
            "DATABASE_URL",
            "REPLAY_TARGET_URL",
            "REPLAY_ALLOWED_HOSTS",
            "FAULT_PROXY_TOKEN",
        ])
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(f"Worker configuration is missing: {', '.join(missing)}")
    if app_env == "production" and len(os.environ["FAULT_PROXY_TOKEN"]) < 32:
        raise ValueError("FAULT_PROXY_TOKEN must contain at least 32 characters")


def main():
    configure_logging()
    validate_environment()
    redis = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("replays", connection=redis, default_timeout=60)
    max_jobs = int(os.environ.get("WORKER_MAX_JOBS", "100"))
    if not 1 <= max_jobs <= 10_000:
        raise ValueError("WORKER_MAX_JOBS must be between 1 and 10000")
    Worker([queue], connection=redis).work(max_jobs=max_jobs)


if __name__ == "__main__":
    main()
