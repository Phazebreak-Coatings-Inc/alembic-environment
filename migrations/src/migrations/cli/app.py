import typer
import os
from typer import Typer
import subprocess
from ..utils import (
    migration_settings as m,
    validate_database_environment,
    ValidDatabaseEnvironments,
    alembic_settings,
)
from typing import Annotated
from ..seeding import execute_seeds
from ..seeding.main import seed_registry
import time
from alembic.config import Config
from alembic.script import ScriptDirectory
from contextlib import contextmanager

app = Typer(pretty_exceptions_show_locals=False)
EnvArg = Annotated[
    ValidDatabaseEnvironments,
    typer.Argument(help="Choose which environment to seed for."),
]


def sh(cmd: str, check=True, **kwargs):
    try:
        subprocess.run(cmd, shell=True, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        typer.secho(f"failed: {cmd}", fg=typer.colors.RED, err=True)
        raise typer.Exit(e.returncode) from None  #


def _pytest(throw: bool = False):
    sh("pytest", check=throw)


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

@app.command(
    help="Start up the migrations database for autogenerating alembic revisions."
)
def up():
    sh("docker pull postgres", check=True)
    sh(
        f"docker run -d --name {m.database_name} -e POSTGRES_USER={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p {m.database_port}:5432 --rm postgres",
        check=True,
    )
    _wait_for_db(engine=m.engine)

@app.command(help="Shut down the migrations database.")
def down():
    sh(f"docker rm -f {m.database_name}", check=True)

@contextmanager
def migrations_database():
    try:
        up()
        yield None
    finally:
        down()


@app.command(help="Seed the database with anything decorated with 'migrations.seed'.")
def seed(env: EnvArg):
    typer.confirm(
        f"This action will run {seed_registry.count_seeds(env)} functions on environment '{env},' Are you sure you want to proceed?",
        abort=True,
    )
    execute_seeds(env)


@app.command(help="Test the alembic revisions generated.")
def test(
    throw: Annotated[
        bool, typer.Option("-t", "--throw", help="Raise on test failure.")
    ] = False,
):
    with migrations_database():
        _pytest(throw)


@app.command(
    help="Start the migrations database to autogenerate a revision, then clean up."
)
def migrate(message: Annotated[str, typer.Option("-m", "--message")] = ""):
    with migrations_database():
        if len(_heads()) > 1:
            sh('alembic merge -m "merge heads" heads')
        sh("alembic upgrade head", check=True)
        sh(
            f'alembic revision --autogenerate -m "{message or "auto"}"',
            check=True,
        )
        _pytest(throw=True)


alembic_env = alembic_settings.env


@app.command(help="Apply reviewed migrations to an environment.")
def apply(
    env: EnvArg = alembic_env,
    target: str = "head",
):
    typer.confirm(f"Upgrade {env} to {target}?", abort=True)
    sh(
        "alembic upgrade target",
        check=True,
        env={**os.environ, "alembic_env": validate_database_environment(env)},
    )
