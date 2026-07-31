import typer
import os
from typing import Annotated, Callable
import functools
import subprocess
from pathlib import Path
from .environments import DatabaseEnvironment, alembic_env
from pydantic import validate_call, BeforeValidator
from .paths import TESTS_MIGRATIONS

VerboseOption = Annotated[
    bool, typer.Option("-v", "--verbose", help="Run in verbose mode.")
]
EnvArg = Annotated[
    DatabaseEnvironment,
    typer.Argument(help="Choose which environment to seed for."),
]
DryRun = Annotated[
    bool, typer.Option("-d", "--dry-run", help="Run without irreversible changes.")
]

def run_steps(fns: list[Callable] | None = None, label: str | None = None):
    fns = fns or []
    with typer.progressbar(
        fns, label=label, width=min(len(fns), 34), show_percent=True
    ) as s:
        for fn in s:
            fn()

def sh(cmd: str, silent=False, check=True, **kwargs) -> subprocess.CompletedProcess:
    if silent:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("text", True)
    try:
        return subprocess.run(cmd, shell=True, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        typer.secho(f"\nFailed: {cmd}", fg=typer.colors.BRIGHT_RED, err=True)
        if output := (e.stderr or e.stdout):
            typer.secho(output.rstrip(), fg=typer.colors.RED, err=True)
        raise typer.Exit(e.returncode) from None

def e(func):
    """Wraps in try except for with exit codes: 0 or 1"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except (typer.Exit, typer.Abort):
            raise
        except Exception as e:
            typer.secho(f"Exiting with code 1: {str(e)}", err=True, fg=typer.colors.RED)
            raise typer.Exit(1)
        raise typer.Exit(0)
    return wrapper

@validate_call
def alembic(cmd: str, env: DatabaseEnvironment = alembic_env):
    sh(
        f"alembic {cmd}",
        check=True,
        env={**os.environ, "ALEMBIC_ENV": env},
    )


TEST_TYPES = ["all", "migrations", "seeds"]


def validate_test_type(t: str) -> "TestType":
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
    if len(alembic_heads()) > 1:
        sh('alembic merge -m "merge heads" heads')
    sh("alembic upgrade head", check=True)
    sh(
        f'alembic revision --autogenerate -m "{message or "auto"}"',
        check=True,
    )


