from typing import Annotated, ClassVar
from functools import lru_cache
from pydantic import BeforeValidator, Field, validate_call, computed_field
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine

JSON_CONFIGS = []
ACTIVE_DATABASE_ENVIRONMENTS = []

def get_json_configs(): ...

def add_database_environment(): ...

def validate_database_environment(): ...

DatabaseEnvironment = Annotated[str, Field(pattern="^()$"), BeforeValidator(validate_database_environment)]

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

    @property
    def profile(self):
        ...


migration_settings = BaseDatabaseSettings(
    database_host="localhost",
    database_port=5431,
    database_username="migrations",
    database_password="migrations_password",
    database_name="migrations",
)

@singleton
class ActiveDatabaseEnvironments:
    __envs__: ClassVar[list[str]]

    @classmethod
    def init_env(env: str)

    @classmethod
    def get_env(env: DatabaseEnvironment)

@lru_cache(maxsize=None)
def validate(env: str) -> str:
    allowed = {"dev", "staging", "prod"}
    if env not in allowed:
        raise ValueError(f"{env!r} not in {allowed}")
    return env


def init_environments(): 
    ...

DEV_ENV = ".env.dev"
STAGING_ENV = ".env.staging"
PROD_ENV = ".env.prod"
ValidDatabaseEnvironments = Literal["dev", "staging", "prod"]
ENVS = ["dev", "staging", "prod"]


def validate_database_environment(env: str) -> ValidDatabaseEnvironments:
    if env not in (envs := ["dev", "staging", "prod"]):
        raise ValueError(f"{env} must be one of {envs}")
    return env  # type: ignore





class DevDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=DEV_ENV)


class StagingDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=STAGING_ENV)


class ProdDatabaseSettings(BaseDatabaseSettings):
    model_config = SettingsConfigDict(env_file=PROD_ENV)


DatabaseSetting = DevDatabaseSettings | StagingDatabaseSettings | ProdDatabaseSettings


def get_database_setting(env: ValidDatabaseEnvironments) -> DatabaseSetting:
    s = None
    match env := validate_database_environment(env):
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
alembic_env = alembic_settings.env

app = typer.Typer(pretty_exceptions_show_locals=False)

VerboseOption = Annotated[
    bool, typer.Option("-v", "--verbose", help="Run in verbose mode.")
]


def run_steps(fns: list[Callable] | None = None, label: str | None = None):
    fns = fns or []
    with typer.progressbar(
        fns, label=label, width=min(len(fns), 34), show_percent=True
    ) as s:
        for fn in s:
            fn()


EnvArg = Annotated[
    ValidDatabaseEnvironments,
    typer.Argument(help="Choose which environment to seed for."),
]
DryRun = Annotated[
    bool, typer.Option("-d", "--dry-run", help="Run without irreversible changes.")
]


def sh(cmd: str, silent=False, check=True, **kwargs):
    if silent:
        kwargs.setdefault("stdout", subprocess.DEVNULL)
        kwargs.setdefault("stderr", subprocess.DEVNULL)
    try:
        subprocess.run(cmd, shell=True, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        typer.secho(f"failed: {cmd}", fg=typer.colors.RED, err=True)
        raise typer.Exit(e.returncode) from None  #


def alembic(cmd: str, env: ValidDatabaseEnvironments = alembic_env):
    sh(
        f"alembic {cmd}",
        check=True,
        env={**os.environ, "alembic_env": validate_database_environment(env)},
    )


type TestTypes = Literal["all", "migrations", "seeds"]

TEST_DIR = Path(__file__).parent.parent.parent.parent / "tests"


def alembic_test(typ: TestTypes = "all", throw: bool = False):
    sh("pytest" if typ == "all" else f"pytest test_{typ}.py", check=throw)


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
    raise RuntimeError("database never accepted connections")
