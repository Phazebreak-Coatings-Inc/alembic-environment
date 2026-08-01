import typer
from typer import Typer
from ...utils import (
    PKG_MODELS,
    INIT_MODELS,
    TABLES_SQL,
    SQLGenerator,
    SQLReverseGenerator,
    ruff_format,
    repair_model_init,
    sh,
    DryRun,
    e,
)
from ..migrations.app import migrate

app = Typer(pretty_exceptions_show_locals=False)


@app.command(help=f"Create models from {TABLES_SQL}")
@e
def g(
    dry_run: DryRun = False,
):
    typer.secho(f"Attempting to generate models from {TABLES_SQL.name}")
    s = SQLGenerator()
    typer.secho(
        f"\nRendered {s.len_models} model(s) from {TABLES_SQL.name}"
    )
    if not dry_run:
        s.write_files()
        repair()
        migrate()
        typer.secho("Wrote files successfully.")

@app.command(help=f"Merge ORM-only columns back into {TABLES_SQL} as comments.")
@e
def rg(dry_run: DryRun = False):
    import models  # noqa: F401
    from sqlmodel import SQLModel
    typer.secho(f"Attempting to reverse generate mixin fields back to {TABLES_SQL.name}")
    r = SQLReverseGenerator(SQLModel.metadata)
    typer.secho(r.write(dry_run=dry_run))

@app.command(help="Auto hook up imports.")
@e
def repair(dry_run: DryRun = False):
    typer.secho(f"Attempting to repair {INIT_MODELS} file")
    repair_model_init(dry_run=dry_run)
    if not dry_run:
        typer.secho(
            f"Successfully wrote new imports."
        )

@app.command(help="CICD pipeline for generating and reverse generating models.")
def cicd():
    g()
    rg()
