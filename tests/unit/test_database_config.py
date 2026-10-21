import pytest

from incident_store.database import normalize_database_url


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "postgres://user:password@db.example.test/app",
            "postgresql+psycopg://user:password@db.example.test/app",
        ),
        (
            "postgresql://user:password@db.example.test/app",
            "postgresql+psycopg://user:password@db.example.test/app",
        ),
        ("sqlite:///./failure_engine.db", "sqlite:///./failure_engine.db"),
    ],
)
def test_database_url_uses_installed_postgresql_driver(source, expected):
    assert normalize_database_url(source) == expected
