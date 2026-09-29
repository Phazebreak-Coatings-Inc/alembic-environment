import os
from collections.abc import Callable
from typing import Any

from pydantic import JsonValue
from collections.abc import Iterator
from functools import cache
from typing import Annotated

from sqlalchemy import URL
from sqlmodel import Session, create_engine, text
from typing import Literal
from time import time

from pydantic_settings import BaseSettings, SettingsConfigDict

import logging

logger = logging.getLogger()

class DatabaseSettings(BaseSettings):
    """Runtime connection settings. Read from DATABASE_* environment variables."""

    model_config = SettingsConfigDict(extra="ignore")

    database_host: str | None = "localhost"
    database_port: int | None = 5432
    database_username: str | None = None
    database_password: str | None = None
    database_name: str | None = None

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
    def engine(self):
        return create_engine(self.database_url, connect_args={"connect_timeout": 3})

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
                        logging.info(
                            f"{self.database_name} ready in "
                            f"{(time.perf_counter() - started) * 1000:.0f}ms",
                        )
                    return
                except Exception as e:
                    last = e
                    if i + 1 >= attempts:
                        break
                    if verbose:
                        logging.info(
                            f"Waiting for {self.database_name} ({i + 1}/{attempts})..."
                        )
                    time.sleep(delay)
        finally:
            engine.dispose()

        raise RuntimeError(
            f"Database connection to {self.database_name} failed after "
            f"{attempts} attempt(s): {last}"
        ) from last


