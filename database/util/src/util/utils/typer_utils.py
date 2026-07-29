import typer
import os
from typing import Annotated, Callable
import subprocess
from pathlib import Path
from .environments import DatabaseEnvironment, alembic_env
from pydantic import validate_call, BeforeValidator
from .paths import TESTS_MIGRATIONS

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
    DatabaseEnvironment,
    typer.Argument(help="Choose which environment to seed for."),
]
DryRun = Annotated[
    bool, typer.Option("-d", "--dry-run", help="Run without irreversible changes.")
]


def sh(cmd: str, silent=False, check=True, **kwargs) -> subprocess.CompletedProcess:
    if silent:
        kwargs.setdefault("stdout", subprocess.DEVNULL)
        kwargs.setdefault("stderr", subprocess.DEVNULL)
    try:
        return subprocess.run(cmd, shell=True, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        typer.secho(f"failed: {cmd}", fg=typer.colors.RED, err=True)
        raise typer.Exit(e.returncode) from None

@validate_call
def alembic(cmd: str, env: DatabaseEnvironment = alembic_env):
    sh(
        f"alembic {cmd}",
        check=True,
        env={**os.environ, "alembic_env": env},
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
    sh(
        "pytest" if typ == "all" else f"pytest {TESTS_MIGRATIONS}/test_{typ}.py",
        check=throw,
    )


def alembic_check():
    sh("alembic upgrade head")
    try:
        sh("alembic check", check=True)
    except subprocess.CalledProcessError as e:
        raise typer.Exit(e.returncode) from None
