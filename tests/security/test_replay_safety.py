import pytest

import replay.environment
from replay.environment import validated_target


def test_replay_requires_allowlisted_target(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REPLAY_TARGET_URL", "http://example.test")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "approved.test")
    with pytest.raises(ValueError, match="not in REPLAY_ALLOWED_HOSTS"):
        validated_target("/ping")


def test_replay_blocks_private_target_without_explicit_local_mode(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REPLAY_TARGET_URL", "https://127.0.0.1")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.delenv("REPLAY_ALLOW_PRIVATE_TARGETS", raising=False)
    with pytest.raises(ValueError, match="non-public"):
        validated_target("/ping")


def test_replay_allows_only_an_explicit_private_synthetic_hostname(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REPLAY_TARGET_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("REPLAY_ALLOWED_PRIVATE_HOSTS", "127.0.0.1")
    assert validated_target("/ping") == "http://127.0.0.1:8080/ping"


def test_replay_rejects_traversal_path_even_for_allowlisted_host(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REPLAY_TARGET_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("REPLAY_ALLOW_PRIVATE_TARGETS", "true")
    with pytest.raises(ValueError, match="path is not safe"):
        validated_target("/../admin")


def test_replay_rejects_allowlisted_hostname_resolving_to_private_address(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REPLAY_TARGET_URL", "https://synthetic.example.test")
    monkeypatch.setenv("REPLAY_ALLOWED_HOSTS", "synthetic.example.test")
    monkeypatch.delenv("REPLAY_ALLOWED_PRIVATE_HOSTS", raising=False)
    monkeypatch.setattr(
        replay.environment.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(ValueError, match="non-public"):
        validated_target("/ping")


def test_proxy_upstream_requires_exact_host_allowlist(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FAULT_UPSTREAM_URL", "https://unapproved.example.test")
    monkeypatch.setenv("FAULT_ALLOWED_HOSTS", "approved.example.test")
    monkeypatch.delenv("FAULT_ALLOWED_PRIVATE_HOSTS", raising=False)

    with pytest.raises(ValueError, match="not in REPLAY_ALLOWED_HOSTS"):
        replay.environment.validate_configured_target(
            "https://unapproved.example.test",
            {"approved.example.test"},
            "/ping",
            private_hosts_env="FAULT_ALLOWED_PRIVATE_HOSTS",
        )
