# database/migrations/tests/conftest.py
import pytest
from database_util.utils import migration_environment
from pytest_alembic.config import Config


@pytest.fixture(scope="session", autouse=True)
def migrations_database():
    try:
        migration_environment.ping()
        yield
        return
    except Exception:
        pass
    with migration_environment.temp():
        yield


@pytest.fixture
def alembic_engine():
    return migration_environment.engine


from pathlib import Path


@pytest.fixture
def alembic_config():
    return Config(
        config_options={
            "file": str(Path(__file__).resolve().parents[3] / "alembic.ini")
        }
    )
