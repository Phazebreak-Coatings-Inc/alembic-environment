import database_client
import pytest
from database_client import (
    DatabaseSettings,
    ensure_database_not_dev,
    get_database_client,
    get_engine,
    get_session,
)
from sqlmodel import Session

DATABASE_ENV = (
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USERNAME",
    "DATABASE_PASSWORD",
)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in (*DATABASE_ENV, "ENV"):
        monkeypatch.delenv(name, raising=False)
    get_database_client.cache_clear()
    get_engine.cache_clear()
    yield
    get_database_client.cache_clear()
    get_engine.cache_clear()


def test_exports_everything_in_all():
    for name in database_client.__all__:
        assert hasattr(database_client, name), name


def test_defaults_are_the_dev_database():
    s = DatabaseSettings()
    assert (
        s.database_url
        == "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db"
    )


def test_reads_database_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "db.example.com")
    monkeypatch.setenv("DATABASE_PORT", "25060")
    s = DatabaseSettings()
    assert (s.database_host, s.database_port) == ("db.example.com", 25060)


def test_to_env_masks_password():
    values = DatabaseSettings().to_env(show_secrets=False)
    assert values["DATABASE_PASSWORD"] == "********"
    assert values["DATABASE_PORT"] == "5432"
    assert set(values) == set(DATABASE_ENV)


def test_to_env_shows_password_by_default():
    assert DatabaseSettings().to_env()["DATABASE_PASSWORD"] == "dev_password"


def test_not_dev_passes_in_dev():
    ensure_database_not_dev()


def test_not_dev_rejects_missing_settings(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_HOST", "db.example.com")
    with pytest.raises(ValueError, match="DATABASE_NAME, DATABASE_PASSWORD"):
        ensure_database_not_dev()


def test_not_dev_passes_when_all_set(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    for name in DATABASE_ENV:
        monkeypatch.setenv(name, "1" if name == "DATABASE_PORT" else "x")
    ensure_database_not_dev()


def test_engine_is_cached():
    assert get_engine() is get_engine()


def test_get_session_yields_session():
    session = next(get_session())
    assert isinstance(session, Session)
    assert session.get_bind() is get_engine()
