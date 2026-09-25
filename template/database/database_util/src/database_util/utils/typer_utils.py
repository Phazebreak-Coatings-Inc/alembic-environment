import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from copier_template.util import cli_exception_handler, sh
from pydantic import BeforeValidator, validate_call

from .environments import DatabaseEnvironment, Revision, alembic_env
from .paths import TESTS_MIGRATIONS

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


def run_steps(fns: list[Callable] | None = None, label: str | None = None):
    fns = fns or []
    total = len(fns)
    for i, fn in enumerate(fns, 1):
        typer.secho(f"{label or 'Running steps'} [{i}/{total}]", fg=typer.colors.CYAN)
        fn()
    typer.secho(f"Completed {total} steps successfully.", fg=typer.colors.GREEN)


@validate_call
def alembic(cmd: str, env: DatabaseEnvironment = alembic_env):
    sh(
        f"alembic {cmd}",
        check=True,
        env={**os.environ, "ALEMBIC_ENV": env},
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
    sh("alembic upgrade head")
    try:
        sh("alembic check", check=True)
    except subprocess.CalledProcessError as e:
        raise typer.Exit(e.returncode) from None


def alembic_migrate(message: str = ""):
    from .environments import alembic_heads

    if len(alembic_heads()) > 1:
        sh('alembic merge -m "merge heads" heads')
    sh("alembic upgrade head", check=True)
    sh(
        f'alembic revision --autogenerate -m "{message or "auto"}"',
        check=True,
    )

class DockerUnavailable(Exception): ...

def require_docker() -> None:
    r = sh("docker info", check=False, silent=True)
    if r.returncode != 0:
        raise DockerUnavailable(
            "Docker isn't available - is Docker Desktop running?\n"
            f"{(r.stderr or r.stdout or '').strip()}"
        )


