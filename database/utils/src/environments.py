import os
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
        raise ValueError(f"'{env}' is not a valid database environment, choose one of {ENVS}")
    return env #type: ignore

DatabaseEnvironment = Annotated[Literal["dev", "staging", "prod"], BeforeValidator(is_valid_database_env)]

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


class MigrationSettings(BaseDatabaseSettings):
    database_host = "localhost" 
    database_port = 5431
    database_username = "migrations"
    database_password = "migrations_password"
    database_name = "migrations"

    def up(self): ...

    def down(self): ...

    def destroy(self): ...

migration_settings = MigrationSettings()

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

app = typer.Typer(pretty_exceptions_show_locals=False)

def _heads() -> list[str]:
    return list(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())

def _wait_for_db(engine, attempts: int = 60, delay: float = 0.5):
    for _ in range(attempts):
        try:
            with engine.connect() as c:
                c.exec_driver_sql("SELECT 1")
            return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("Couldn't start database")
