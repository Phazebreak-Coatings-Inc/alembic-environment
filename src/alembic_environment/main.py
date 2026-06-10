from typer import Typer
from typing import Annotated
import copier
import typer
import subprocess
from pathlib import Path

   
WORKSPACES = ["models", "migrations"]

PACKAGES = [
    "alembic>=1.18.4",
    "copier>=9.15.1",
    "sqlalchemy>=2.0.50",
    "sqlmodel>=0.0.38",
    "typer>=0.26.6",
    "pytest-alembic>=0.12.1",
    "pytest>=9.0.3",
    "pydantic-settings>=2.14.1",
    "psycopg[binary]>=3.3.4",
    "ruff>=0.15.15",
    "tomlkit>=0.15.0",
    "sqlacodegen>=4.0.3",
    "inflection>=0.5.1",
]
app = Typer(pretty_exceptions_show_locals=False)

def sh(cmd: str, check=True, **kwargs):
    try:
        subprocess.run(cmd, shell=True, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        typer.secho(f"failed: {cmd}", fg=typer.colors.RED, err=True)
        raise typer.Exit(e.returncode) from None  #

@app.command(help="Initialize a new alembic-environment project.")
def init(dest: Annotated[str, typer.Argument(help="Directory to initialize project in.")] = "."):
    dest_path = Path(dest).resolve()
    pyproject_path = dest_path / "pyproject.toml"
    if not pyproject_path.exists():
        sh("uv init")
    copier.run_copy("gh:Phazebreak-Coatings-Inc/alembic-environment", dest)
    repair()

@app.command(help="Update an existing alembic-environment project.")
def update(abort: Annotated[bool, typer.Option("--abort", "-a", help="If the abort flag is triggered, this will reset the attempt to update the copier project. Prudent when the changes are too much to resolve.")] = False):
    match abort:
        case False:
            typer.confirm(
                "Are you sure you want to update? If you need to abort mid-update, it will trigger a 'git reset.' Make sure to save all uncommitted changes.",
                abort=True,
            )
            subprocess.run("copier update --conflict inline", shell=True, check=True)
        case True:
            typer.confirm(
                "Are you sure you want to abort? This will trigger a 'git reset.'",
                abort=True
            )
            subprocess.run("git reset", shell=True, check=True)
            subprocess.run("git checkout .", shell=True, check=True)
            subprocess.run("git clean -d -i", shell=True, check=True)
    repair()

@app.command(help="Hook up dependencies and workspaces correctly.")
def repair():
    print("Adding dependencies and workspaces ...")
    sh("uv sync")
    sh(f'uv add --workspace {" ".join(WORKSPACES)}')
    sh(f'uv add {" ".join(PACKAGES)}')
    print("Repair completed successfully.")
