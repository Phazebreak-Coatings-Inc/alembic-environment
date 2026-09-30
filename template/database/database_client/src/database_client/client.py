import logging
import os
import time
from collections.abc import Iterator
from functools import cache
from typing import Annotated, cast

from fastapi import Depends
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, Engine
from sqlmodel import Session, create_engine, text

logger = logging.getLogger(__name__)

class DatabaseSettings(BaseSettings):
    """Runtime connection settings. Read from DATABASE_* environment variables."""

    model_config = SettingsConfigDict(extra="ignore")

    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_username: str = "dev_user"
    database_password: str = "dev_password"
    database_name: str = "dev_db"

    @property
    def database_url(self) -> str:
        return URL.create(
            "postgresql+psycopg",
            username=self.database_username,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)

    @property
    def engine(self) -> Engine:
        return create_engine(
            self.database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )

    def ping(
        self, attempts: int = 1, delay: float = 0.5, verbose: bool = False
    ) -> None:
        engine = self.engine
        started = time.perf_counter()
        last: Exception | None = None
        try:
            for i in range(attempts):
                try:
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                    if verbose:
                        logger.info(
                            "%s ready in %.0fms",
                            self.database_name,
                            (time.perf_counter() - started) * 1000,
                        )
                    return
                except Exception as e:
                    last = e
                    if i + 1 >= attempts:
                        break
                    if verbose:
                        logger.info(
                            "Waiting for %s (%d/%d)...",
                            self.database_name,
                            i + 1,
                            attempts,
                        )
                    time.sleep(delay)
        finally:
            engine.dispose()

        raise RuntimeError(
            f"Database connection to {self.database_name} failed after "
            f"{attempts} attempt(s): {last}"
        ) from last

    def to_env(self, show_secrets: bool = True) -> dict[str, str]:
        return {
            name.upper(): "********"
            if name == "database_password" and not show_secrets
            else str(value)
            for name, value in self.model_dump().items()
        }

def database_settings_lookup(env: str) -> DatabaseSettings:
    try:
        from database_util.utils import DatabaseEnvironment, get_database_settings
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_* are not set and database_util is not installed to resolve them."
        ) from exc
    return get_database_settings(cast(DatabaseEnvironment, env))


def get_database_host(env: str) -> str:
    return database_settings_lookup(env).database_host


def get_database_port(env: str) -> int:
    return database_settings_lookup(env).database_port


def get_database_name(env: str) -> str:
    return database_settings_lookup(env).database_name


def get_database_username(env: str) -> str:
    return database_settings_lookup(env).database_username


def get_database_password(env: str) -> str:
    return database_settings_lookup(env).database_password

@cache
def get_database_client() -> DatabaseSettings:
    return DatabaseSettings()

@cache
def get_engine() -> Engine:
    return get_database_client().engine


def ensure_database_not_dev() -> None:
    env = os.environ.get("ENV", "dev")
    if env == "dev":
        return
    client = get_database_client()
    if missing := sorted(set(type(client).model_fields) - client.model_fields_set):
        raise ValueError(
            f"ENV={env} but {', '.join(m.upper() for m in missing)} are not set. "
            "Dev defaults are only used when ENV=dev."
        )


def ensure_database_connection() -> None:
    get_database_client().ping()


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


SessionDI = Annotated[Session, Depends(get_session)]
