import os
from contextlib import contextmanager
from pathlib import Path
import time
from typing import Annotated, Callable, Literal, cast
from abc import abstractmethod

import typer
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BeforeValidator, validate_call
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine

DEV_ENV = ".env.dev"
STAGING_ENV = ".env.staging"
PROD_ENV = ".env.prod"
ENVS = ["dev", "staging", "prod"]


def is_valid_database_env(env: str) -> "DatabaseEnvironment":
    if env not in ENVS:
        raise ValueError(
            f"'{env}' is not a valid database environment, choose one of {ENVS}"
        )
    return env  # type: ignore


DatabaseEnvironment = Annotated[
    Literal["dev", "staging", "prod"], BeforeValidator(is_valid_database_env)
]


class BaseDatabaseSettings(BaseSettings):
    database_host: str | None = "localhost"
    database_port: int | None = 5432
    database_username: str | None = None
    database_password: str | None = None
    database_name: str | None = None

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.database_username}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def engine(self):
        return create_engine(self.database_url)
   
    @abstractmethod
    def up(self): ...

    @abstractmethod
    def down(self): ...

    @abstractmethod
    def destroy(self): ...

    @contextmanager
    def temp(self):
        try:
            self.up()
            yield None
        finally:
            self.down()

def wait_for_database(engine, attempts: int = 60, delay: float = 0.5):
    for _ in range(attempts):
        try:
            with engine.connect() as c:
                c.exec_driver_sql("SELECT 1")
            return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("Couldn't start database")

class MigrationSettings(BaseDatabaseSettings):
    database_host = "localhost"
    database_port = 5431
    database_username = "migrations"
    database_password = "migrations_password"
    database_name = "migrations"

    def up(self):
        from .typer_utils import run_steps, sh
        m = self
        run_steps(
            fns=[
                lambda: sh("docker pull postgres", check=True),
                lambda: sh(
                    f"docker run -d --name {m.database_name} -e POSTGRES_USER={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p {m.database_port}:5432 --rm postgres",
                    check=True,
                ),
                lambda: wait_for_database(engine=m.engine),
            ],
            label="Starting Migrations Database",
        )   
    
    def down(self): 
        from .typer_utils import run_steps, sh
        m = self
        run_steps(
            fns=[lambda: sh(f"docker rm -f {m.database_name}", check=True, silent=True)],
            label="Shutting Down Migrations Database",
        )

    def destroy(self): 
        return self.down()

migration_settings = MigrationSettings()
migration_database = migration_settings.temp


class DevDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=DEV_ENV)

    def up(self): ...

    def down(self): ...

    def destroy(self): ...


class StagingDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=STAGING_ENV)

    def up(self): ...

    def down(self): ...

    def destroy(self): ...


class ProdDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=PROD_ENV)

    def up(self): ...

    def down(self): ...

    def destroy(self): ...


DatabaseSetting = DevDatabaseSettings | StagingDatabaseSettings | ProdDatabaseSettings


@validate_call
def get_database_setting(env: DatabaseEnvironment) -> DatabaseSetting:
    s = None
    match env:
        case "dev":
            s = DevDatabaseSettings()
        case "staging":
            s = StagingDatabaseSettings()
        case "prod":
            s = ProdDatabaseSettings()
    return s


class AlembicSettings(BaseSettings):
    env = "dev"
    auto_seed: bool = True


alembic_settings = AlembicSettings()
alembic_env: DatabaseEnvironment = cast(DatabaseEnvironment, alembic_settings.env)

def alembic_heads() -> list[str]:
    return list(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
