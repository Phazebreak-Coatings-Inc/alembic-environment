import os
from sqlalchemy import MetaData, create_engine
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal

APP_METADATA = MetaData()
DEV_ENV = ".env.dev"
STAGING_ENV = ".env.staging"
PROD_ENV = ".env.prod"
ValidDatabaseEnvironments = Literal["dev", "staging", "prod"]

def validate_database_environment(env: str) -> ValidDatabaseEnvironments:
    if env not in (envs := ["dev", "staging", "prod"]):
            raise ValueError(f"{env} must be one of {envs}")
    return env #type: ignore

class BaseDatabaseSettings(BaseSettings):
    database_host: str | None = "localhost"
    database_port: int | None = 5432
    database_username: str | None = None
    database_password: str | None = None
    database_name: str | None = None

    @property
    def database_url(self) -> str:
        return (f"postgresql+psycopg://{self.database_username}:{self.database_password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}")

    @property
    def engine(self):
        return create_engine(self.database_url)

migration_settings = BaseDatabaseSettings(
    database_host = "localhost",
    database_port = 5431,
    database_username = "migrations",
    database_password = "migrations_password",
    database_name = "migrations",
)

class DevDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=DEV_ENV)

class StagingDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=STAGING_ENV)

class ProdDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=PROD_ENV)


DatabaseSetting = DevDatabaseSettings | StagingDatabaseSettings | ProdDatabaseSettings

def get_database_setting(env: ValidDatabaseEnvironments) -> DatabaseSetting :
    s = None
    match (env := validate_database_environment(env)):
        case "dev":
            s = DevDatabaseSettings()
        case "staging":
            s = StagingDatabaseSettings()
        case "prod":
            s = ProdDatabaseSettings()
    return s

class AlembicSettings(BaseSettings):
    env: ValidDatabaseEnvironments = "dev"
    auto_seed: bool = True

alembic_settings = AlembicSettings()
