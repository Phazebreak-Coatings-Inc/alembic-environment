from contextlib import contextmanager
import time
import subprocess
from typing import Annotated, Literal, cast, ClassVar
from abc import abstractmethod, ABC
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BeforeValidator, validate_call
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from .paths import ENV_DEV, ENV_PROD, ENV_STAGING, ENV_DEV_COMPOSE, PKG_PROD, PKG_STAGING

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

def wait_for_database(engine, attempts: int = 60, delay: float = 0.5):
    for _ in range(attempts):
        try:
            with engine.connect() as c:
                c.exec_driver_sql("SELECT 1")
            return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("Couldn't start database")

class BaseDatabaseSettings(ABC, BaseSettings):
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
    def up(self) -> None: ...

    @abstractmethod
    def down(self) -> None: ...

    @abstractmethod
    def destroy(self) -> None: ...

    @abstractmethod
    def test(self) -> bool: ...

    @contextmanager
    def temp(self):
        try:
            self.up()
            yield None
        finally:
            self.down()

class TerraformedDatabaseSettings(BaseDatabaseSettings):
    __cwd__: ClassVar[Path | None] = None

    @classmethod
    def set_cwd(cls, p: Path) -> None:
        cls.__cwd__ = p

    @classmethod
    def get_cwd(cls) -> Path:
        if not cls.__cwd__: 
            raise ValueError(f"Cwd for {cls.__name__} was never set")
        p = cls.__cwd__
        if not p.exists():
            raise FileNotFoundError(f"Cwd for {cls.__name__} does not exist at: {p}")
        if not p.is_dir():
            raise TypeError(f"Cwd for {cls.__name__} must be a directory")
        return p 

    @property
    def planned(self) -> bool:
        return (self.get_cwd() / "main.tfplan").exists()

    def tf(self, cmd: str) -> subprocess.CompletedProcess:
        from .typer_utils import sh
        return sh(f"terraform {cmd}", cwd=self.get_cwd(), check=True, silent=False)

    def plan(self):
        self.tf("init")
        self.tf("plan -out main.tfplan")

    def apply(self):
        if not self.planned:
            self.plan()
        self.tf("apply main.tfplan")

    def test(self) -> bool:
        try:
            self.plan()
            return True
        except Exception:
            return False

    def destroy(self):
        self.tf("destroy")

    @property
    def outputs(self):
        print(f"completed: {self.tf('output -json')}")

    @property
    def database_url(self) -> str:
        # load ouputs here
        return (
            f"postgresql+psycopg://{self.database_username}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


class MigrationSettings(BaseDatabaseSettings):
    def up(self):
        from .typer_utils import run_steps, sh

        m = self
        run_steps(
            fns=[
                lambda: sh("docker pull postgres", check=True, silent=True),
                lambda: sh(
                    f"docker run -d --name {m.database_name} -e POSTGRES_USER={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p {m.database_port}:5432 --rm postgres",
                    check=True,
                    silent=True,
                ),
                lambda: wait_for_database(engine=m.engine),
            ],
            label="Starting Migrations Database",
        )

    def down(self):
        from .typer_utils import run_steps, sh

        m = self
        run_steps(
            fns=[
                lambda: sh(f"docker rm -f {m.database_name}", check=True, silent=True)
            ],
            label="Shutting Down Migrations Database",
        )

    def destroy(self):
        return self.down()

    def test(self): #Can't really test it no? Lol
        return True

migration_settings = MigrationSettings(
    database_host="localhost",
    database_port=5431,
    database_username="migrations",
    database_password="migrations_password",
    database_name="migrations",
)
migration_database = migration_settings.temp

class DevDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_DEV)

    def up(self):
        from .typer_utils import run_steps, sh
        sh(
            f"docker compose -f {ENV_DEV_COMPOSE} up", check=True
        )

    def down(self):
        from .typer_utils import run_steps, sh
        sh(
            f"docker compose -f {ENV_DEV_COMPOSE} down"
        )

    def destroy(self):
        from .typer_utils import run_steps, sh
        sh(
            f"docker compsoe -f {ENV_DEV_COMPOSE} down -v"
        )

    def test(self):
        return True

class StagingDatabaseSettings(TerraformedDatabaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_STAGING)

    def up(self): ...

    def down(self): ...

    def destroy(self): ...

StagingDatabaseSettings.set_cwd(PKG_STAGING)

class ProdDatabaseSettings(TerraformedDatabaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PROD)
    
    def up(self): ...

    def down(self): ...

    def destroy(self): ...

ProdDatabaseSettings.set_cwd(PKG_PROD)

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
    env: DatabaseEnvironment = "dev"
    auto_seed: bool = True


alembic_settings = AlembicSettings()
alembic_env: DatabaseEnvironment = cast(DatabaseEnvironment, alembic_settings.env)


def alembic_heads() -> list[str]:
    return list(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
