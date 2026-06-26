import os
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

from migrations._cli.seeding.main import SEEDS_DIRECTORY
from migrations.utils import (
    ENVS,
    app,
    DryRun,
    EnvArg,
    VerboseOption,
    _heads,
    alembic_test,
    _wait_for_db,
    alembic_env,
    run_steps,
    sh,
    validate_database_environment,
    alembic,
)
from migrations.utils import (
    migration_settings as m,
)

from .seeding import execute_seeds, generate_seed_file


@app.command(
    help="Start up the migrations database for autogenerating alembic revisions."
)
def up(v: VerboseOption = False):
    run_steps(
        fns=[
            lambda: sh("docker pull postgres", check=True, silent=not v),
            lambda: sh(
                f"docker run -d --name {m.database_name} -e POSTGRES_USER={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p {m.database_port}:5432 --rm postgres",
                check=True,
                silent=not v,
            ),
            lambda: _wait_for_db(engine=m.engine),
        ],
        label="Starting Migrations Database",
    )


@app.command(help="Shut down the migrations database.")
def down():
    run_steps(
        fns=[lambda: sh(f"docker rm -f {m.database_name}", check=True, silent=True)],
        label="Shutting Down Migrations Database",
    )


@contextmanager
def migrations_database():
    try:
        up()
        yield None
    finally:
        down()


@app.command(help="Seed the database with anything decorated with 'migrations.seed'.")
def seed(
    env: EnvArg,
    n: Annotated[
        str | None,
        typer.Option(
            "--generate",
            "-g",
            help=f"Generate a seed file with '--g {{ name }}' It will arrive in ...{Path(*SEEDS_DIRECTORY.parts[-4:])}. The environment variable is for specifying in what environment the seed should run.",
        ),
    ] = None,
    d: DryRun = False,
):
    if n:
        generate_seed_file(env=env, name=n, dry_run=d)
        return
    execute_seeds(env=env, dry_run=d, confirm=True)


@app.command(help="Test the alembic revisions generated.")
def test(
    throw: Annotated[
        bool, typer.Option("-t", "--throw", help="Raise on test failure.")
    ] = False,
    seed: Annotated[bool, typer.Option("-s", "--seed", help="Test seed runs")] = False,
):
    with migrations_database():
        _pytest(typ="migrations" if not seed else "seeds", throw=throw)


def alembic_migrate(message: str = ""):
    if len(_heads()) > 1:
        sh('alembic merge -m "merge heads" heads')
    sh("alembic upgrade head", check=True)
    sh(
        f'alembic revision --autogenerate -m "{message or "auto"}"',
        check=True,
    )


@app.command(
    help="Start the migrations database to autogenerate a revision, then clean up."
)
def migrate(message: Annotated[str, typer.Option("-m", "--message")] = ""):
    with migrations_database():
        alembic_migrate(message)
        alembic_test(throw=True)


@app.command(help="Apply reviewed migrations to an environment.")
def apply(
    env: EnvArg = alembic_env,
    target: str = "head",
):
    typer.confirm(f"Upgrade {env} to {target}?", abort=True)
    alembic("upgrade target", env)


def alembic_check():
    sh("alembic upgrade head")
    try:
        sh("alembic check", check=True)
    except subprocess.CalledProcessError as e:
        raise typer.Exit(e.returncode) from None


@app.command(help="Check if the database needs to be migrated.")
def check():
    with migrations_database():
        alembic_check()


@app.command(help="Generate the first (baseline) revision, even if empty.")
def init():
    if _heads():
        typer.secho(
            "Revisions already exist, use 'migrate' instead.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    with migrations_database():
        sh(
            'alembic -x initial=true revision --autogenerate -m "initial"',
            check=True,
        )
        alembic_test(throw=True)


@app.command(
    help="Run a autonomous CICD workflow that checks for drift, tests, and commits to a separate branch with a pull-request."
)
def cicd(
    exclude: Annotated[
        list[str],
        typer.Option("--exclude", "-e", help="Exclude from being run on certain envs"),
    ],
):
    with migrations_database():
        try:
            alembic_check()
            alembic_test(throw=False)
            return
        except subprocess.CalledProcessError as e:
            if len(_heads()) > 1:
                sh('alembic merge -m "merge heads" heads')
            sh("alembic upgrade head", check=True)
            sh(
                f"alembic revision --autogenerate -m auto",
                check=True,
            )
        try:
            b = f"cicd/alembic-migration-{uuid.uuid4()}"
            sh(f"git switch -c {b}")
            sh("uvx ruff format .")
            sh("git commit -a")
            sh("git push")
            sh(f"gh pr create --fill --base main --head {b}")

        except Exception as e:
            raise Exception(
                f"Error creating a separate branch and PR with new migrations: {e}"
            )


@app.command(
    help="Apply migrations to staging and prod. Only use this once the migrations are actually on main, else you could have broken versioning."
)
def cicd_apply():
    for env in ["staging", "prod"]:
        apply(env)  # type: ignore
