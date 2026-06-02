import os
from sqlalchemy import MetaData, create_engine
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

APP_METADATA = MetaData()
DEV_ENV = ".env.dev"
STAGING_ENV = ".env.staging"
PROD_ENV = ".env.prod"

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

class MigrationGeneratorSettings(BaseDatabaseSettings):
    database_host = "localhost"
    database_port = 5432
    database_username = "migrations"
    database_password = "migrations_password"
    database_name = "migrations"

class DevDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=DEV_ENV)

class StagingDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=DEV_ENV)

class ProdDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=DEV_ENV)

_ENVIRONMENTS = {"dev": DevDatabaseSettings,
                 "staging": StagingDatabaseSettings,
                 "prod": ProdDatabaseSettings}

@lru_cache
def get_settings() -> BaseDatabaseSettings:
    return _ENVIRONMENTS[os.getenv("APP_ENV", "dev")]()
