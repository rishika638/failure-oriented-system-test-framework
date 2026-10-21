import pytest

from worker.main import validate_environment


def test_worker_environment_requires_production_connections_and_targets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://redis.example.test/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://db.example.test/app")
    monkeypatch.setenv("REPLAY_TARGET_URL", "https://proxy.example.test")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "proxy.example.test")
    monkeypatch.setenv("FAULT_PROXY_TOKEN", "t" * 40)
    validate_environment()

    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        validate_environment()


def test_worker_rejects_short_production_proxy_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://redis.example.test/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://db.example.test/app")
    monkeypatch.setenv("REPLAY_TARGET_URL", "https://proxy.example.test")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "proxy.example.test")
    monkeypatch.setenv("FAULT_PROXY_TOKEN", "too-short")

    with pytest.raises(ValueError, match="FAULT_PROXY_TOKEN"):
        validate_environment()
