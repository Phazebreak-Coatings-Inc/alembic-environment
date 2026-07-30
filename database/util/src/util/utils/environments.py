from contextlib import contextmanager
import typer
import os
import json
import time
import subprocess
from typing import Annotated, Literal, cast, ClassVar, Self, Mapping, TypedDict, Any
from abc import abstractmethod, ABC
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BeforeValidator, validate_call, BaseModel, SecretStr, model_validator
from functools import cached_property
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlmodel import Session
from .paths import (
    ENV_DEV,
    ENV_PROD,
    ENV_STAGING,
    ENV_DEV_COMPOSE,
    PKG_PROD,
    PKG_STAGING,
)

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

    def ping(self, verbose: bool = False) -> float:
        e = self.engine
        if verbose:
            print(f"[alembic-environment] Attempting to ping {self.database_name} ...")
        start = time.perf_counter()
        try:
            with e.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise RuntimeError(f"Database connection to {self.database_name} failed: {e}") from e
        t = (time.perf_counter() - start) * 1000
        if verbose:
            print(f"[alembic-environment] Successfully pinged {self.database_name} in {t:.1f}ms")
        return t

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

class TerraformOutput(BaseModel):
    value: str | int | SecretStr
    sensitive: bool
    type: str

    @model_validator(mode="after")
    def wrap_sensitive(self):
        if self.sensitive and not isinstance(self.value, SecretStr):
            self.value = SecretStr(str(self.value))
        return self

class TerraformedDatabaseSettings[OutputsShape: Mapping = Mapping](
    BaseDatabaseSettings
):
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
    def plan_file(self) -> Path:
        return self.get_cwd() / "main.tfplan"

    @property
    def planned(self) -> bool:
        return self.plan_file.exists()

    def tf(self, cmd: str, **kwargs) -> subprocess.CompletedProcess:
        from .typer_utils import sh

        return sh(f"terraform {cmd}", cwd=self.get_cwd(), check=True, silent=False, text=True, **kwargs)

    def plan(self) -> subprocess.CompletedProcess:
        self.tf("init")
        return self.tf("plan -out main.tfplan")

    def apply(self):
        self.plan()
        try:
            self.tf("apply main.tfplan")
        finally:
            self.plan_file.unlink(missing_ok=True)

    def test(self) -> bool:
        try:
            self.plan()
            return True
        except Exception:
            return False

    def up(self) -> None:
        self.apply()
        self.ping(verbose=True)

    def down(self) -> None:
        raise Exception(
            "Terraformed databases cannot be 'downed' like containerized databases."
        )

    def destroy(self) -> subprocess.CompletedProcess:
        typer.confirm(
            "Are you sure you want to destroy? This will permanently delete your database.",
            abort=True,
        )
        typer.confirm(
            "For realsies?",
            abort=True,
        )
        return self.tf("destroy")

    @cached_property
    def outputs(self) -> dict[str, TerraformOutput]:
        result = self.tf("output -json -no-color", capture_output=True)
        return {k: TerraformOutput.model_validate(v) for k, v in json.loads(result.stdout).items()}

    def get_output(self, key: str) -> Any:
        out = self.outputs[key]
        return out.value.get_secret_value() if isinstance(out.value, SecretStr) else out.value

    @abstractmethod
    def map_outputs(self) -> None: ...

    @property
    def database_url(self) -> str:
        self.map_outputs()
        return (
            f"postgresql+psycopg://{self.database_username}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    def temp(self) -> None:
        raise Exception("Can't spin up 'temp' for a terraformed database")

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
                lambda: self.ping(),
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

    def test(self):  # Can't really test it no? Lol
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
    def up(self):
        from .typer_utils import run_steps, sh

        sh(f"docker compose -f {ENV_DEV_COMPOSE} up", check=True)
        self.ping(verbose=True)

    def down(self):
        from .typer_utils import run_steps, sh

        sh(f"docker compose -f {ENV_DEV_COMPOSE} down")

    def destroy(self):
        from .typer_utils import run_steps, sh

        sh(f"docker compose -f {ENV_DEV_COMPOSE} down -v")

    def test(self):
        with self.temp():
            self.ping(verbose=True)


dev_settings = DevDatabaseSettings(
    database_host="localhost",
    database_port=5432,
    database_name="dev_db",
    database_username="dev_user",
    database_password="dev_password",
)
dev_database = dev_settings.temp


class StagingOutputs(TypedDict):
    database_host: str
    database_port: int
    staging_name: str
    staging_username: str
    staging_password: str


class StagingDatabaseSettings(TerraformedDatabaseSettings[StagingOutputs]):
    def sanitize(self): ...

    def stage(self): ...

    def map_outputs(self): 
        self.database_host = self.get_output("database_host")
        self.database_port = self.get_output("database_port")
        self.database_name = self.get_output("staging_name")
        self.database_username = self.get_output("staging_username")
        self.database_password = self.get_output("staging_password")

StagingDatabaseSettings.set_cwd(PKG_PROD)

staging_settings = StagingDatabaseSettings()


class ProdOutputs(TypedDict):
    database_host: str
    database_port: int
    prod_name: str
    prod_username: str
    prod_password: str

class ProdDatabaseSettings(TerraformedDatabaseSettings[ProdOutputs]):
    def map_outputs(self):
        self.database_host = self.get_output("database_host")
        self.database_port = self.get_output("database_port")
        self.database_name = self.get_output("prod_name")
        self.database_username = self.get_output("prod_username")
        self.database_password = self.get_output("prod_password")


ProdDatabaseSettings.set_cwd(PKG_PROD)

prod_settings = ProdDatabaseSettings()

DatabaseSetting = DevDatabaseSettings | StagingDatabaseSettings | ProdDatabaseSettings


@validate_call
def get_database_setting(env: DatabaseEnvironment) -> DatabaseSetting:
    s = None
    match env:
        case "dev":
            s = dev_settings
        case "staging":
            s = staging_settings
        case "prod":
            s = prod_settings
    return s


class AlembicSettings(BaseSettings):
    env: DatabaseEnvironment = "dev"
    auto_seed: bool = True


alembic_settings = AlembicSettings()
alembic_env: DatabaseEnvironment = cast(DatabaseEnvironment, alembic_settings.env)


def alembic_heads() -> list[str]:
    return list(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
