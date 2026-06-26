import ast
from typing import Annotated

import typer
from migrations._cli.app import migrate
from typer import Typer

from models._cli.sql.main import (
    INIT_FILE,
    MODELS_DIR,
    SQL_DIR,
    SQLGenerator,
    ruff_format,
)

app = Typer(pretty_exceptions_show_locals=False)


@app.command(help=f"Create models, validators, and typeddicts from {SQL_DIR}")
def g(
    dry_run: Annotated[
        bool,
        typer.Option(
            "-dr", "--dry-run", help="Generate the model without writing to disk."
        ),
    ] = False,
):
    s = SQLGenerator()
    print(
        f"\nRendered {s.len_models} model(s) from {[f.name for f in s.files]}: \n\n{s.code}"
    )
    if not dry_run:
        s.write_files()
        repair()
        migrate()
        print("Wrote files successfully.")


@app.command(help="Auto hook up imports.")
def repair():
    lines: list[str] = []
    all_names: list[str] = []
    for f in sorted(MODELS_DIR.rglob("*.py")):
        if f.name == "__init__.py":
            continue
        tree = ast.parse(f.read_text())
        names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        for n in tree.body:
            if isinstance(n, ast.Assign):
                names += [t.id for t in n.targets if isinstance(t, ast.Name)]
        if not names:
            continue
        module = ".".join(f.relative_to(MODELS_DIR).with_suffix("").parts)
        lines.append(f"from .{module} import " + ", ".join(names))
        all_names += names
    body = "\n".join(lines)
    body += "\n\n__all__ = [" + ", ".join(f'"{n}"' for n in all_names) + "]\n"
    INIT_FILE.write_text(ruff_format(body))
