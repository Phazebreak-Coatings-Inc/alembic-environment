import ast
import contextlib
import copy
import importlib
import re
import json
import logging
import os
import pkgutil
import subprocess
import time
import tomllib
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, TypedDict, cast, get_type_hints

import inflection
import logfire
import sqlglot
import typer
from alembic import op
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from copier_template.util import (
    TerraformOutput,
    TerraformOutputError,
    TFSecret,
    TFSettingsMixin,
    TFVar,
    cli_exception_handler,
    sh,
)
from logfire.propagate import attach_context, get_context
from pydantic import (
    AliasChoices,
    BeforeValidator,
    PrivateAttr,
    Secret,
    SecretStr,
    validate_call,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlacodegen.generators import SQLModelGenerator
from sqlalchemy import URL, MetaData, create_engine, create_mock_engine, text
from sqlglot import exp
from sqlmodel import Session

BackfillFunction = Callable[[Session], None]
BackfillRegistry = dict[str, list[BackfillFunction]]

BACKFILLS: BackfillRegistry = defaultdict(list)

BACKFILL_TEMPLATE = """
from sqlmodel import Session
from database_core import backfill


@backfill("{rev}")
def backfill_{rev}(session: Session) -> None:
    ...
"""


class BackfillException(Exception): ...


ENVS = ["dev", "staging", "prod", "mig"]


def is_valid_database_env(env: str) -> DatabaseEnvironment:
    if env not in ENVS:
        raise ValueError(
            f"'{env}' is not a valid database environment, choose one of {ENVS}"
        )
    return env  # type: ignore


DatabaseEnvironment = Annotated[
    Literal["dev", "staging", "prod", "mig"], BeforeValidator(is_valid_database_env)
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
        return create_engine(self.database_url, connect_args={"connect_timeout": 3})

    @abstractmethod
    def get_environment_str(self) -> str: ...

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
                        typer.secho(
                            f"{self.database_name} ready in "
                            f"{(time.perf_counter() - started) * 1000:.0f}ms",
                            fg=typer.colors.GREEN,
                        )
                    return
                except Exception as e:
                    last = e
                    if i + 1 >= attempts:
                        break
                    if verbose:
                        typer.secho(
                            f"Waiting for {self.database_name} ({i + 1}/{attempts})..."
                        )
                    time.sleep(delay)
        finally:
            engine.dispose()

        raise RuntimeError(
            f"Database connection to {self.database_name} failed after "
            f"{attempts} attempt(s): {last}"
        ) from last

    def up(self, startup: bool = False) -> None:
        try:
            self.ping()
            typer.secho(
                f"Database '{self.get_environment_str()}' is already up.",
                fg=typer.colors.GREEN,
            )
        except Exception:
            self.start()
            self.ping(attempts=60, verbose=True)
            startup = True

        if startup:
            run_steps(fns=self.up_steps(), label="Running startup steps...")

    @abstractmethod
    def start(self) -> None: ...

    def up_steps(self) -> list[Callable]:
        return [
            self.upgrade,
            lambda: self.seed(interactive=False),
        ]

    @abstractmethod
    def down(self) -> None: ...

    @abstractmethod
    def destroy(self) -> None: ...

    @abstractmethod
    def test(self) -> bool: ...

    def upgrade(self):
        from database_util.clis.migrations.app import apply

        apply(self.get_environment_str(), interactive=False)  # type: ignore

    def seed(self, interactive: bool = False):
        from database_util.clis.migrations.app import seed

        if (env := self.get_environment_str()) in ["dev", "prod"]:
            return seed(env=env, i=interactive)  # type: ignore
        if env == "staging":
            return self.stage()

    def stage(self): ...

    @contextmanager
    def temp(self):
        try:
            try:
                self.ping()
                yield None
            except Exception:
                self.up()
                yield None
        finally:
            self.down()


DIR_DATABASE = Path(__file__).parent.parent.parent.parent
DIR_ROOT = DIR_DATABASE.parent
ROOT_ENV = DIR_ROOT / ".env"


class CLISettings(TFSettingsMixin, BaseSettings):
    """Deploy time configuration read from the project .env. Never used at runtime."""

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tf_cloud_organization: str | None = TFVar(
        "TF_CLOUD_ORGANIZATION",
        description="HCP Terraform organization that owns the workspace.",
    )
    tf_workspace: str | None = TFVar(
        "TF_WORKSPACE",
        description="HCP Terraform workspace for the database cluster.",
    )
    do_token: SecretStr | None = TFSecret(
        "TF_VAR_do_token",
        description="DigitalOcean personal access token.",
        validation_alias=AliasChoices("DO_TOKEN", "TF_VAR_DO_TOKEN"),
    )
    logfire_api_key: SecretStr | None = TFSecret(
        "LOGFIRE_API_KEY",
        description="Logfire API key. Lets Terraform create the project and write token.",
    )

    def require(self, *names: str) -> None:
        if missing := [n.upper() for n in names if not getattr(self, n)]:
            raise ValueError(f"Missing {', '.join(missing)} in {ROOT_ENV}")


ROOT_PYPROJECT = DIR_ROOT / "pyproject.toml"


def read_project_name() -> str:
    try:
        name = tomllib.loads(ROOT_PYPROJECT.read_text())["project"]["name"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "database"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{name}-database".lower()).strip("-")
    return slug or "database"


class TerraformedDatabaseSettings[OutputsShape: Mapping = Mapping](
    BaseDatabaseSettings
):
    __cwd__: ClassVar[Path | None] = None
    _outputs_cache: dict[str, TerraformOutput] | None = PrivateAttr(default=None)

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

    def tf(self, cmd: str, check: bool = True, silent: bool = False, **kwargs):
        return sh(
            f"terraform {cmd}",
            cwd=self.get_cwd(),
            check=check,
            silent=silent,
            text=True,
            env=CLISettings().tf_env(TF_VAR_project_name=read_project_name()),
        )

    def plan(self) -> subprocess.CompletedProcess:
        CLISettings().require("do_token", "logfire_api_key")
        self.tf("init")
        return self.tf("plan -out main.tfplan")

    def apply(self):
        self.plan()
        try:
            self.tf("apply main.tfplan")
        finally:
            self.plan_file.unlink(missing_ok=True)
            self._outputs_cache = None

    def test(self) -> bool:
        try:
            self.ping()
            return True
        except Exception:
            return False

    def start(self) -> None:
        self.apply()

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

    @property
    def outputs(self) -> dict[str, TerraformOutput]:
        if self._outputs_cache is None:
            r = self.tf("output -json -no-color", check=False, silent=True)
            self._outputs_cache = (
                {}
                if r.returncode != 0 or not (r.stdout or "").strip()
                else {
                    k: TerraformOutput.model_validate(v)
                    for k, v in json.loads(r.stdout).items()
                }
            )
        return self._outputs_cache

    def get_output(self, key: str) -> Any:
        outputs = self.outputs
        if key not in outputs:
            available = json.dumps(
                {
                    k: "**********" if isinstance(v.value, Secret) else v.value
                    for k, v in outputs.items()
                },
                indent=2,
            )
            raise TerraformOutputError(
                f"No terraform output '{key}' for '{self.get_environment_str()}'. "
                f"Available: {available or '(none - has this environment been applied?)'}"
            )
        out = outputs[key]
        return (
            out.value.get_secret_value() if isinstance(out.value, Secret) else out.value
        )

    @abstractmethod
    def map_outputs(self) -> None: ...

    def create_database_url(self, username: str, password: str) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=username,
            password=password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    @property
    def database_url(self) -> str:
        self.map_outputs()
        u = self.database_username
        p = self.database_password
        if u is None or p is None:
            raise ValueError("Expected database_user and database_password")
        return self.create_database_url(u, p).render_as_string(hide_password=False)

    @property
    def admin_engine(self):
        from sqlalchemy import create_engine

        self.map_outputs()
        return create_engine(
            self.create_database_url(
                self.get_output("admin_username"), self.get_output("admin_password")
            ),
            connect_args={"connect_timeout": 3},
        )

    def grant(self) -> None:
        self.map_outputs()
        admin = URL.create(
            "postgresql+psycopg",
            username=self.get_output("admin_username"),
            password=self.get_output("admin_password"),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )
        with create_engine(admin).begin() as c:
            c.exec_driver_sql(
                f'GRANT ALL ON SCHEMA public TO "{self.database_username}"'
            )
        typer.secho(
            f"Ensured grant on schema public to {self.database_username}",
            fg=typer.colors.GREEN,
        )

    def temp(self) -> None:
        raise Exception("Can't spin up 'temp' for a terraformed database")

    def up_steps(self) -> list[Callable]:
        return [
            self.grant,
            self.upgrade,
            lambda: self.seed(interactive=False),
        ]


IMAGE = "postgres:18-alpine"


def image_exists() -> bool:
    return sh(f"docker image inspect {IMAGE}", check=False, silent=True) == 0


def pull_postgres(attempts: int = 3, backoff: float = 2.0) -> None:
    if image_exists():
        return
    last = None
    for i in range(attempts):
        try:
            sh(f"docker pull {IMAGE}", check=True, silent=True)
            return
        except Exception as e:
            last = e
            if image_exists():
                return
            if i < attempts - 1:
                time.sleep(backoff * (2**i))
    raise RuntimeError(f"Could not pull {IMAGE}: {last}")


def run_steps(fns: list[Callable] | None = None, label: str | None = None):
    fns = fns or []
    total = len(fns)
    for i, fn in enumerate(fns, 1):
        typer.secho(f"{label or 'Running steps'} [{i}/{total}]", fg=typer.colors.CYAN)
        with logfire.span("step {name}", name=fn.__name__, label=label, index=i):
            fn()
    typer.secho(f"Completed {total} steps successfully.", fg=typer.colors.GREEN)


class DockerUnavailable(Exception): ...


def require_docker() -> None:
    r = sh("docker info", check=False, silent=True)
    if r.returncode != 0:
        raise DockerUnavailable(
            "Docker isn't available - is Docker Desktop running?\n"
            f"{(r.stderr or r.stdout or '').strip()}"
        )


class MigrationSettings(BaseDatabaseSettings):
    def start(self):
        m = self
        run_steps(
            fns=[
                require_docker,
                pull_postgres,
                lambda: sh(
                    f"docker run -d --name {m.database_name} -e POSTGRES_USER={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p {m.database_port}:5432 --rm postgres:18-alpine",
                    check=True,
                    silent=False,
                ),
                lambda: self.ping(attempts=60),
            ],
            label="Starting Migrations Database",
        )

    def up_steps(self) -> list[Callable]:
        return []

    def down(self):
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

    def get_environment_str(self) -> str:
        return "mig"


migration_settings = MigrationSettings(
    database_host="127.0.0.1",
    database_port=5431,
    database_username="migrations",
    database_password="migrations_password",
    database_name="migrations",
)
WS_ENVIRONMENTS = DIR_DATABASE / "database_environments"
PKG_CLUSTERS = WS_ENVIRONMENTS / "clusters"
PKG_DEV = PKG_CLUSTERS / "dev"
ENV_DEV_COMPOSE = PKG_DEV / "compose.dev.yml"


class DevDatabaseSettings(BaseDatabaseSettings):
    def start(self):
        run_steps(
            fns=[
                require_docker,
                lambda: sh(f"docker compose -f {ENV_DEV_COMPOSE} up -d", check=True),
            ],
            label="Starting dev database",
        )

    def down(self):
        sh(f"docker compose -f {ENV_DEV_COMPOSE} down")

    def destroy(self):
        sh(f"docker compose -f {ENV_DEV_COMPOSE} down -v")

    def test(self):
        with self.temp():
            return True

    def get_environment_str(self) -> str:
        return "dev"


dev_settings = DevDatabaseSettings(
    database_host="127.0.0.1",
    database_port=5432,
    database_name="dev_db",
    database_username="dev_user",
    database_password="dev_password",
)


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

    def get_environment_str(self) -> str:
        return "staging"


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

    def get_environment_str(self) -> str:
        return "prod"


prod_settings = ProdDatabaseSettings()

DatabaseSetting = (
    DevDatabaseSettings
    | StagingDatabaseSettings
    | ProdDatabaseSettings
    | MigrationSettings
)


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
        case "mig":
            s = migration_settings
    return s


class AlembicSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALEMBIC_")

    env: DatabaseEnvironment = "dev"
    auto_seed: bool = True


alembic_settings = AlembicSettings()
alembic_env: DatabaseEnvironment = cast(DatabaseEnvironment, alembic_settings.env)


class RevisionError(Exception): ...


ALEMBIC_INI = DIR_ROOT / "alembic.ini"


def script_dir() -> ScriptDirectory:
    if not ALEMBIC_INI.is_file():
        raise FileNotFoundError(f"Missing {ALEMBIC_INI}")
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


def validate_revs(revs: list[str]) -> list[str]:
    try:
        return [s.revision for s in script_dir().get_revisions(tuple(revs))]
    except CommandError as e:
        raise RevisionError(f"unknown revision(s) {revs}: {e}") from e


def is_valid_rev(rev: str) -> str:
    return validate_revs([rev])[0]


Revision = Annotated[str, BeforeValidator(is_valid_rev)]


@validate_call
def backfill(rev: Revision):
    def dec(fn) -> BackfillFunction:
        if not (sesh := get_type_hints(fn).get("session", None)):
            raise BackfillException(
                f"session must be passed as a type hint in fn {fn.__name__}"
            )
        if not (isinstance(sesh, type) and issubclass(sesh, Session)):
            raise BackfillException(
                f"`session` of {fn.__name__} must be a sqlmodel.Session subclass"
            )
        BACKFILLS[rev].append(fn)
        return fn

    return dec


def get_backfills(rev: str) -> list[BackfillFunction]:
    name = f"migrations.backfills.{rev}"
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return []
    return BACKFILLS[rev]


def run_backfill(rev: str) -> None:
    """Called from a revision's upgrade(). No-op when the revision has no backfill."""
    if not (fns := get_backfills(rev)):
        return
    with Session(bind=op.get_bind()) as session:
        for fn in fns:
            with logfire.span("backfill {backfill}", backfill=fn.__name__, rev=rev):
                fn(session)
        session.flush()


WS_MIGRATIONS = DIR_DATABASE / "migrations"
PKG_MIGRATIONS = WS_MIGRATIONS / "src" / "migrations"
DIR_BACKFILLS = PKG_MIGRATIONS / "backfills"


def write_backfill_stub(rev: str) -> Path:
    DIR_BACKFILLS.mkdir(parents=True, exist_ok=True)
    (DIR_BACKFILLS / "__init__.py").touch()
    p = DIR_BACKFILLS / f"{rev}.py"
    if not p.exists():
        p.write_text(BACKFILL_TEMPLATE.format(rev=rev))
        typer.secho(f"Wrote backfill stub {p}", fg=typer.colors.GREEN)
    else:
        typer.secho(
            f"Backfill already exists for this revision at {p}", fg=typer.colors.YELLOW
        )
    return p


migration_database = migration_settings.temp
dev_database = dev_settings.temp
PKG_PROD = PKG_CLUSTERS / "prod"


StagingDatabaseSettings.set_cwd(PKG_PROD)


ProdDatabaseSettings.set_cwd(PKG_PROD)


def alembic_heads() -> list[str]:
    return list(script_dir().get_heads())


def latest_rev() -> str:
    """The single head revision id."""
    heads = alembic_heads()
    if not heads:
        raise RevisionError("No revisions exist yet - run 'migrations init' first.")
    if len(heads) > 1:
        raise RevisionError(f"History has branched across {len(heads)} heads: {heads}")
    return heads[0]


GIT_BOT_NAME = "github-actions[bot]"
GIT_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


@contextmanager
def git_bot(message: str, path: Path = Path(".")):
    yield
    sh(f'git add -- "{path}"', check=True)
    if sh("git diff --cached --quiet", check=False).returncode == 0:
        typer.secho("[git-bot]: nothing to commit.", fg=typer.colors.YELLOW)
        return
    sh(
        f'git -c user.name="{GIT_BOT_NAME}" -c user.email="{GIT_BOT_EMAIL}" '
        f'commit -m "{message}"',
        check=True,
    )
    sh("git push", check=True)


def ruff_format(code: str) -> str:
    p = subprocess.run(
        "uvx ruff format -", shell=True, input=code, capture_output=True, text=True
    )
    return p.stdout if p.returncode == 0 else code


def model_exports(init: Path) -> list[str]:
    for n in ast.parse(init.read_text()).body:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets
        ):
            if isinstance(n.value, ast.List):
                return [e.value for e in n.value.elts if isinstance(e, ast.Constant)]  # type: ignore
    return []


def repair_model_init(dry_run: bool = False):
    lines: list[str] = ["from .base_model import SQLModelBase"]
    all_names: list[str] = ["SQLModelBase"]
    for d in sorted(p for p in PKG_MODELS.iterdir() if (p / "__init__.py").exists()):
        names = model_exports(d / "__init__.py")
        if not names:
            continue
        lines.append(f"from .{d.name} import " + ", ".join(names))
        all_names += names

    body = "\n".join(lines)
    rebuilds = [n for n in all_names if not n.endswith("Base")]
    if rebuilds:
        body += "\n\n" + "\n".join(f"{n}.model_rebuild()" for n in rebuilds)
    body += "\n\n__all__ = [" + ", ".join(f'"{n}"' for n in all_names) + "]\n"
    if not dry_run:
        INIT_MODELS.write_text(ruff_format(body))
    if dry_run:
        typer.secho(f"Would have generated: \n\n {body}", fg=typer.colors.YELLOW)


WS_MODELS = DIR_DATABASE / "models"
TABLES_SQL = WS_MODELS / "tables.sql"
PKG_MODELS = WS_MODELS / "src" / "models"
TESTS_MIGRATIONS = WS_MIGRATIONS / "tests"
PKG_ENVIRONMENTS = WS_ENVIRONMENTS / "src" / "database_environments"
DIR_SEEDS = PKG_MIGRATIONS / "seeds"
INIT_MODELS = PKG_MODELS / "__init__.py"
DIR_VERSIONS = PKG_MIGRATIONS / "versions"
ENV_PROD = PKG_PROD / ".env.prod"
ENV_DEV = PKG_DEV / ".env.dev"
PKG_STAGING = PKG_CLUSTERS / "staging"
ENV_STAGING = PKG_STAGING / ".env.staging"


SEEDABLE_ENVS = ["dev", "prod"]


def is_valid_seedable_env(env: str) -> SeedableDatabaseEnvironment:
    if env not in SEEDABLE_ENVS:
        raise ValueError(
            f"'{env}' is not a valid database environment, choose one of {SEEDABLE_ENVS}"
        )
    return env  # type: ignore


SeedFunction = Callable[[Session], None]
SeedRegistry = dict[DatabaseEnvironment, list[SeedFunction]]
RequiresRegistry = dict[SeedFunction, list[SeedFunction]]
SeedableDatabaseEnvironment = Annotated[
    Literal["dev", "prod"], BeforeValidator(is_valid_seedable_env)
]
SeedableEnvArg = Annotated[
    SeedableDatabaseEnvironment,
    typer.Argument(
        help="Choose which environment to seed for, either 'dev' or 'prod' because staging is a separate flow."
    ),
]


class SeedingException(Exception): ...


SEEDS: SeedRegistry = defaultdict(list)
REQUIRES: RequiresRegistry = {}
SEED_TEMPLATE = """from models import *
from sqlmodel import Session
from database_core import seed

@seed(['{env}'])
def {name}(session: Session) -> None:
    ...
"""


@validate_call
def generate_seed_file(
    env: SeedableDatabaseEnvironment, name: str, dry_run: bool = False
):
    n = inflection.underscore(name)
    p = DIR_SEEDS / f"{n}.py"
    if p.exists():
        typer.confirm(
            f"{p.name} already exists, are you sure you want to overwrite it?",
            abort=True,
        )
    else:
        p.touch()

    t = SEED_TEMPLATE.format(env=env, name=n)

    if dry_run:
        typer.secho(
            f"Would write new seed file to {p}: \n\n{t}\n", fg=typer.colors.YELLOW
        )

    p.write_text(t)
    typer.secho(f"Wrote new seed file to {p}: \n\n{t}\n", fg=typer.colors.GREEN)


@validate_call
def seed(
    envs: list[SeedableDatabaseEnvironment], requires: list[SeedFunction] | None = None
):
    def dec(fn) -> SeedFunction:
        if not (sesh := get_type_hints(fn).get("session", None)):
            raise SeedingException(
                f"session must be passed as a type hint in fn {fn.__name__}"
            )
        if not (isinstance(sesh, type) and issubclass(sesh, Session)):
            raise SeedingException(
                f"`session` of {fn.__name__} must be a sqlmodel.Session subclass"
            )
        REQUIRES[fn] = requires or []
        for env in envs:
            SEEDS[env].append(fn)
        return fn

    return dec


@validate_call
def count_seeds(env: SeedableDatabaseEnvironment) -> int:
    return len(SEEDS[env])


@validate_call
def get_seeds(env: SeedableDatabaseEnvironment) -> list[SeedFunction]:
    return SEEDS[env]


@validate_call
def sort_seeds(env: SeedableDatabaseEnvironment) -> list[SeedFunction]:
    fns = get_seeds(env)
    registered, out, done, stack = set(fns), [], set(), set()

    def visit(fn):
        if fn in done:
            return
        if fn in stack:
            raise SeedingException(f"circular seed dependency at '{fn.__name__}'")
        if fn not in registered:
            raise SeedingException(
                f"'{fn.__name__}' is required but not registered for environment '{env}'"
            )
        stack.add(fn)
        for dep in REQUIRES.get(fn, []):
            visit(dep)
        stack.discard(fn)
        done.add(fn)
        out.append(fn)

    for fn in fns:
        visit(fn)

    return out


def load_seeds() -> None:
    import migrations.seeds as pkg

    for m in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"{pkg.__name__}.{m.name}")


@validate_call
def execute_seeds(
    env: SeedableDatabaseEnvironment, dry_run: bool = False, interactive: bool = True
):
    load_seeds()
    errors: list[tuple[str, Exception]] = []
    with Session(get_database_setting(env).engine) as s:

        def make_step(fn):
            def step():
                try:
                    with (
                        logfire.span("seed {seed}", seed=fn.__name__, env=env),
                        s.begin_nested(),
                    ):
                        fn(s)
                except Exception as e:
                    errors.append((fn.__name__, e))

            return step

        fns = [make_step(fn) for fn in sort_seeds(env)]

        if len(fns) == 0:
            typer.secho(
                f"Found 0 seeds for environment '{env}'...", fg=typer.colors.YELLOW
            )
            return

        if interactive and not dry_run:
            typer.confirm(
                f"This action will run {count_seeds(env)} functions on environment '{env},' Are you sure you want to proceed?",
                abort=True,
            )

        run_steps(label=f"Seeding '{env}' environment", fns=fns)

        if errors:
            s.rollback()
            details = "\n".join(f"  {name}: {e}" for name, e in errors)
            raise SeedingException(f"{len(errors)} seed(s) failed:\n{details}")
        if dry_run:
            s.rollback()
            typer.secho(
                f"Successfully ran and rolled-back {len(fns)} seeding functions in '{env}' environment.",
                fg=typer.colors.GREEN,
            )
            return

        typer.secho(
            f"Successfully ran {len(fns)} seeding functions in '{env}' environment.",
            fg=typer.colors.GREEN,
        )
        s.commit()


FileKind = Literal["base", "mixin", "model"]


class Model:
    def __init__(self, class_def: ast.ClassDef):
        self.cls = class_def

    @property
    def name(self) -> str:
        return self.cls.name

    def get_path(self, file: FileKind):
        return PKG_MODELS / inflection.underscore(self.name) / f"{file}.py"

    @property
    def fields(self) -> list[ast.AnnAssign]:
        return [
            s
            for s in self.cls.body
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
        ]

    @staticmethod
    def is_relationship(field: ast.AnnAssign) -> bool:
        return (
            isinstance(field.value, ast.Call)
            and isinstance(field.value.func, ast.Name)
            and field.value.func.id == "Relationship"
        )

    @property
    def relationships(self) -> list[ast.AnnAssign]:
        return [f for f in self.fields if self.is_relationship(f)]

    def relationship_targets(self, known: set[str]) -> set[str]:
        out: set[str] = set()
        for f in self.relationships:
            for n in ast.walk(f.annotation):
                if isinstance(n, ast.Name) and n.id in known:
                    out.add(n.id)
                elif isinstance(n, ast.Constant) and n.value in known:
                    out.add(n.value)
        return out - {self.name}

    def class_to_mixin(self) -> str:
        return f"class {self.name}Mixin: ...\n"

    def class_to_model(self, known: set[str]) -> str:
        lines = [
            "from typing import TYPE_CHECKING, List, Optional",
            "from sqlmodel import Relationship",
            "from ..base_model import SQLModelBase",
            f"from .base import {self.name}Base",
            f"from .mixin import {self.name}Mixin",
        ]
        if targets := sorted(self.relationship_targets(known)):
            lines += ["", "if TYPE_CHECKING:"] + [
                f"    from ..{inflection.underscore(t)}.model import {t}"
                for t in targets
            ]
        lines += [
            "",
            "",
            f"class {self.name}({self.name}Mixin, SQLModelBase, {self.name}Base, table=True):",
        ]
        lines += [f"    {ast.unparse(r)}" for r in self.relationships] or ["    pass"]
        return "\n".join(lines) + "\n"

    def class_to_base(self) -> str:
        """SQLModel base: the same class without table=True or relationships."""
        node = copy.deepcopy(self.cls)
        node.name = f"{self.name}Base"
        node.keywords = [k for k in node.keywords if k.arg != "table"]
        node.decorator_list = []
        node.body = [
            s
            for s in node.body
            if not (isinstance(s, ast.AnnAssign) and self.is_relationship(s))
        ] or [ast.Pass()]
        return "from sqlmodel import SQLModel, Field\n\n\n" + ast.unparse(node)

    def class_to_init(self) -> str:
        names = [
            f"{self.name}Base",
            self.name,
        ]
        imports = f"from .base import {names[0]}\nfrom .model import {names[1]}\n"
        exports = "__all__ = [" + ", ".join(f'"{n}"' for n in names) + "]\n"
        return imports + "\n" + exports


class SQLGenerator:
    def __init__(self, dry_run: bool = False):
        g = SQLModelGenerator
        e = migration_settings.engine
        with migration_database():
            with e.begin() as c:
                c.exec_driver_sql(self.tables_file.read_text())

            md = MetaData()
            md.reflect(bind=e)
            self.code = ruff_format(g(md, e, options=[]).generate())

    @property
    def tables_file(self) -> Path:
        return TABLES_SQL

    @property
    def tree(self) -> ast.Module:
        return ast.parse(self.code)

    @property
    def models(self):
        return [Model(n) for n in self.tree.body if isinstance(n, ast.ClassDef)]

    @property
    def len_models(self) -> int:
        return len(self.models)

    @property
    def header(self) -> str:
        return "\n".join(
            ast.get_source_segment(self.code, n) or ""
            for n in self.tree.body
            if isinstance(n, (ast.Import, ast.ImportFrom))
        )

    def write_files(self):
        known = {m.name for m in self.models}
        for model in self.models:
            directory = model.get_path("model").parent
            directory.mkdir(parents=True, exist_ok=True)

            model.get_path("base").write_text(
                ruff_format(f"{self.header}\n\n\n{model.class_to_base()}")
            )
            model.get_path("model").write_text(ruff_format(model.class_to_model(known)))

            mixin_path = model.get_path("mixin")
            if not mixin_path.exists():
                mixin_path.write_text(ruff_format(model.class_to_mixin()))

            (directory / "__init__.py").write_text(ruff_format(model.class_to_init()))


DIALECT = "postgres"


class SQLParseError(Exception): ...


def get_creates(sql: str) -> list[exp.Create]:
    return [s for s in sqlglot.parse(sql) if isinstance(s, exp.Create)]


def create_to_columns(create: exp.Create) -> list[exp.ColumnDef]:
    return list(create.find_all(exp.ColumnDef))


def create_to_table(create: exp.Create) -> exp.Table:
    return create.this.find(exp.Table)


class SQLMergeError(Exception): ...


def as_comment(col: exp.ColumnDef) -> exp.ColumnDef:
    col._commented = True
    return col


def is_comment(col: exp.ColumnDef) -> bool:
    return getattr(col, "_commented", False)


def merge_columns(
    c1: list[exp.ColumnDef],
    c2: list[exp.ColumnDef],
    comment: bool = True,
):
    names = {c.name for c in c1}
    merged = []
    for col in c2:
        if col.name in names:
            raise SQLMergeError(f"Column '{col.name}' is already defined")
        merged.append(as_comment(col) if comment else col)
    return merged


def render_create(table: str, cols: list[exp.ColumnDef]) -> str:
    real = [c for c in cols if not is_comment(c)]
    commented = [c for c in cols if is_comment(c)]
    body = ",\n  ".join(c.sql(dialect=DIALECT) for c in real)
    out = f"CREATE TABLE {table} (\n  {body}"
    if commented:
        out += "\n  " + "\n  ".join("-- " + c.sql(dialect=DIALECT) for c in commented)
    return out + "\n)"


def get_sql_from_orm(metadata: MetaData):
    ddl = []
    engine = create_mock_engine(
        "postgresql://",
        lambda sql, *a, **k: ddl.append(str(sql.compile(dialect=engine.dialect))),
    )
    metadata.create_all(engine, checkfirst=False)
    return ddl


def comment_out(sql: str) -> str:
    return "\n".join(f"-- {line}" for line in sql.splitlines())


class SQLReverseGenerator:
    def __init__(self, metadata: MetaData):
        self.metadata = metadata

    @property
    def orm_creates(self) -> dict[str, exp.Create]:
        creates = {}
        for ddl in get_sql_from_orm(self.metadata):
            for c in get_creates(ddl):
                creates[create_to_table(c).name] = c
        return creates

    @property
    def sql_creates(self) -> dict[str, exp.Create]:
        return {create_to_table(c).name: c for c in get_creates(TABLES_SQL.read_text())}

    def reverse_table(self, table: str) -> str:
        sql_cols = create_to_columns(self.sql_creates[table])
        sql_names = {c.name for c in sql_cols}
        orm_only = [
            c
            for c in create_to_columns(self.orm_creates[table])
            if c.name not in sql_names
        ]
        return render_create(table, sql_cols + merge_columns(sql_cols, orm_only))

    def generate(self) -> dict[str, str]:
        orm = self.orm_creates
        out = {t: self.reverse_table(t) for t in self.sql_creates if t in orm}
        for t, create in orm.items():
            if t not in self.sql_creates:
                out[t] = comment_out(create.sql(dialect=DIALECT, pretty=True))
        return out

    def write(self, path: Path = TABLES_SQL, dry_run: bool = False) -> str:
        extra = [
            s
            for s in sqlglot.parse(path.read_text())
            if s is not None and not isinstance(s, exp.Create)
        ]
        if extra:
            raise SQLParseError(
                f"{path.name} contains {len(extra)} non-CREATE statement(s) that would be "
                f"lost: {[s.sql(dialect=DIALECT)[:40] for s in extra]}"
            )

        if not self.sql_creates:
            raise SQLParseError(f"No CREATE TABLE statements found in {path}")

        reversed = self.generate()
        ordered = list(self.sql_creates) + [
            t for t in reversed if t not in self.sql_creates
        ]

        parts = []
        for t in ordered:
            sql = reversed.get(t) or self.sql_creates[t].sql(
                dialect=DIALECT, pretty=True
            )
            parts.append(sql if sql.lstrip().startswith("--") else sql + ";")
        body = "\n\n".join(parts) + "\n"

        if not dry_run:
            path.write_text(body)

        return body


TRACE_ENV_VARS = ("TRACEPARENT", "TRACESTATE")
DEPLOYED_ENVS = ("staging", "prod")

logger = logging.getLogger("alembic-environment")

_TELEMETRY_CONFIGURED = False


class TelemetrySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    alembic_env: DatabaseEnvironment = alembic_env
    logfire_token: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""

    @property
    def telemetry_enabled(self) -> bool:
        return bool(self.logfire_token or self.otel_exporter_otlp_endpoint)

    def resolve_token(self) -> None:
        if self.logfire_token or self.alembic_env not in DEPLOYED_ENVS:
            return
        with contextlib.suppress(TerraformOutputError, FileNotFoundError):
            self.logfire_token = str(prod_settings.get_output("logfire_token"))

    def setup_telemetry(self, service_name: str | None = None) -> bool:
        global _TELEMETRY_CONFIGURED
        if _TELEMETRY_CONFIGURED:
            return self.telemetry_enabled
        self.resolve_token()
        if self.otel_exporter_otlp_endpoint:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = self.otel_exporter_otlp_endpoint
        if self.otel_exporter_otlp_headers:
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = self.otel_exporter_otlp_headers
        logfire.configure(
            service_name=service_name or read_project_name(),
            environment=self.alembic_env,
            token=self.logfire_token or None,
            send_to_logfire="if-token-present" if self.telemetry_enabled else False,
            console=False,
        )
        logfire.instrument_sqlalchemy()
        logging.getLogger().addHandler(logfire.LogfireLoggingHandler())
        _TELEMETRY_CONFIGURED = True
        self.check_telemetry()
        return self.telemetry_enabled

    def check_telemetry(self) -> None:
        if self.telemetry_enabled or self.alembic_env not in DEPLOYED_ENVS:
            return
        msg = (
            f"env={self.alembic_env} but telemetry is unconfigured. "
            "Set LOGFIRE_TOKEN or OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        logger.warning(msg)
        typer.secho(msg, fg=typer.colors.YELLOW, err=True)


def setup_telemetry() -> bool:
    return TelemetrySettings().setup_telemetry()


@contextmanager
def step(message: str, name: str, **attrs) -> Iterator[None]:
    typer.secho(message, fg=typer.colors.YELLOW)
    with logfire.span(name, **attrs):
        yield


def trace_env() -> dict[str, str]:
    """The current trace context as environment variables for a subprocess."""
    return {k.upper(): v for k, v in get_context().items()}


@contextmanager
def inherited_trace() -> Iterator[None]:
    """Continue a trace started by a parent process."""
    carrier = {k.lower(): os.environ[k] for k in TRACE_ENV_VARS if k in os.environ}
    with attach_context(carrier):
        yield


RevisionOption = Annotated[
    Revision, typer.Option("-r", "--revision", help="Which alembic revision to target.")
]
VerboseOption = Annotated[
    bool, typer.Option("-v", "--verbose", help="Run in verbose mode.")
]
EnvArg = Annotated[
    DatabaseEnvironment,
    typer.Argument(help="Which database environment to target."),
]
DryRun = Annotated[
    bool, typer.Option("-d", "--dry-run", help="Run without irreversible changes.")
]
Interactive = Annotated[
    bool,
    typer.Option("-i", "--interactive", help="Whether to confirm application."),
]


@validate_call
def alembic(cmd: str, env: DatabaseEnvironment = alembic_env):
    sh(
        f"alembic {cmd}",
        check=True,
        cwd=DIR_ROOT,
        env={"ALEMBIC_ENV": env, **trace_env()},
    )


e = cli_exception_handler

TEST_TYPES = ["all", "migrations", "seeds"]


def validate_test_type(t: str) -> TestType:
    if t not in TEST_TYPES:
        raise ValueError()
    return t


TestType = Annotated[str, BeforeValidator(validate_test_type)]

TEST_DIR = Path(__file__).parent.parent.parent.parent / "tests"


@validate_call
def alembic_test(typ: TestType = "all", throw: bool = False):
    target = TESTS_MIGRATIONS if typ == "all" else f"{TESTS_MIGRATIONS}/test_{typ}.py"
    sh(f"pytest {target}", check=throw)


def alembic_check():
    alembic("upgrade head", "mig")
    try:
        alembic("check", "mig")
    except subprocess.CalledProcessError as e:
        raise typer.Exit(e.returncode) from None


def alembic_migrate(message: str = ""):
    if len(alembic_heads()) > 1:
        alembic('merge -m "merge heads" heads', "mig")
    alembic("upgrade head", "mig")
    alembic(f'revision --autogenerate -m "{message or "auto"}"', "mig")
