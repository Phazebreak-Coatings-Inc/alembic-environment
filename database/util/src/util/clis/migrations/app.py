import subprocess
import uuid
from pathlib import Path
from typing import Annotated
from pydantic import validate_call

import typer

from ...utils import (
    DryRun,
    EnvArg,
    VerboseOption,
    alembic_heads,
    alembic_test,
    alembic_env,
    sh,
    alembic,
    migration_settings as ms,
    migration_database as mdb,
    alembic_check,
    DIR_SEEDS,
)

from .seeding import execute_seeds, generate_seed_file


app = typer.Typer()


@app.command(
    help="Start up the migrations database for autogenerating alembic revisions."
)
@validate_call
def up(v: VerboseOption = False):
    return ms.up()


@app.command(help="Shut down the migrations database.")
def down():
    return ms.down()


@app.command(help="Seed the database with anything decorated with 'migrations.seed'.")
def seed(
    env: EnvArg,
    n: Annotated[
        str | None,
        typer.Option(
            "--generate",
            "-g",
            help=f"Generate a seed file with '--g {{ name }}' It will arrive in ...{Path(*DIR_SEEDS.parts[-4:])}. The environment variable is for specifying in what environment the seed should run.",
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
    with mdb():
        alembic_test(typ="migrations" if not seed else "seeds", throw=throw)


def alembic_migrate(message: str = ""):
    if len(alembic_heads()) > 1:
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
    with mdb():
        alembic_migrate(message)
        alembic_test(throw=True)


@app.command(help="Apply reviewed migrations to an environment.")
def apply(
    env: EnvArg = alembic_env,
    target: str = "head",
):
    typer.confirm(f"Upgrade {env} to {target}?", abort=True)
    alembic("upgrade target", env)


@app.command(help="Check if the database needs to be migrated.")
def check():
    with mdb():
        alembic_check()


@app.command(help="Generate the first (baseline) revision, even if empty.")
def init():
    if alembic_heads():
        typer.secho(
            "Revisions already exist, use 'migrate' instead.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    with mdb():
        sh(
            'alembic -x initial=true revision --autogenerate -m "initial"',
            check=True,
        )
        alembic_test(throw=True)


@app.command(
    help="Run a autonomous CICD workflow that checks for drift, tests, and commits to a separate branch with a pull-request."
)
def cicd():
    with mdb():
        try:
            alembic_check()
            alembic_test(throw=False)
            return
        except subprocess.CalledProcessError:
            if len(alembic_heads()) > 1:
                sh('alembic merge -m "merge heads" heads')
            sh("alembic upgrade head", check=True)
            sh(
                "alembic revision --autogenerate -m auto",
                check=True,
            )
        try:
            # TODO: this needs to be replaced from main to whatever the current branch is and auto merged or else tons of spam, etc etc ...
            raise NotImplementedError("Current solution is bad")
            b = f"cicd/alembic-migration-{uuid.uuid4()}"
            sh(f"git switch -c {b}")
            sh("uvx ruff format .")
            sh("git commit -a")
            sh("git push")
            sh(f"gh pr create --fill --base main --head {b}")

        except Exception as e:
            raise Exception(f"Error creating merging new migrations: {e}")


@app.command(
    help="Apply migrations to staging and prod. Only use this once the migrations are actually on main, else you could have broken versioning."
)
def cicd_apply():
    for env in ["staging", "prod"]:
        apply(env)  # type: ignore
