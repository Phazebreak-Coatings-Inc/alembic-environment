import os
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

from migrations._cli.seeding.main import SEEDS_DIRECTORY
from migrations.utils import (
    app,
    DryRun,
    EnvArg,
    VerboseOption,
    _heads,
    _pytest,
    _wait_for_db,
    alembic_env,
    run_steps,
    sh,
    validate_database_environment,
)
from migrations.utils import (
    migration_settings as m,
)

from .seeding import execute_seeds, generate_seed_file
from .seeding.main import seed_registry


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
        generate_seed_file(
            env=env, 
            name=n, 
            dry_run=d
        )
        return
    execute_seeds(
        env=env, 
        dry_run=d, 
        confirm=True
    )


@app.command(help="Test the alembic revisions generated.")
def test(
    throw: Annotated[
        bool, typer.Option("-t", "--throw", help="Raise on test failure.")
    ] = False,
    seed: Annotated[bool, typer.Option("-s", "--seed", help="Test seed runs")] = False,
):
    with migrations_database():
        _pytest(typ="migrations" if not seed else "seeds", throw=throw)


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
        _pytest(throw=True)
