from typer import Typer
import typer
from models.cli.templates import template_registry
from models.cli.templates.main import TEMPLATES_DIR
from models.cli.sql.main import SQLGenerator, SQL_DIR, MODELS_DIR, INIT_FILE
from typing import Annotated
from pathlib import Path
import ast

app = Typer(pretty_exceptions_show_locals=False)

@app.command(help=f"Create a model from a jinja2 template in {TEMPLATES_DIR}, or pass --sql or -s to generate from {SQL_DIR}")
def g(
    template: Annotated[str, typer.Argument(help="Template name, default is sqlmodel")] = "",
    file_name: Annotated[str, typer.Argument(help="The name of your file")] = "",
    var: Annotated[list[str], typer.Option("--var", "-v", help="key=value, repeatable")] = list(),
    sql: Annotated[bool, typer.Option("--sql", "-s", help=f"Generate from {SQL_DIR}")] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "-dr", "--dry-run", help="Generate the model without writing to disk."
        ),
    ] = False,
):
    if sql:
        s = SQLGenerator()
        print(f"\nRendered {s.len_models} model(s) from {[f.name for f in s.files]}: \n\n{s.code}")
        if not dry_run:
            s.write_files()

    else: 
        if not template:
            print(f"Template name not provided: choose from {list(template_registry.get_options().keys())}")
            raise typer.Exit(1)
        if not file_name:
            print("File name not provided, use: generate_model {template} {file_name}")
            raise typer.Exit(1)
        ctx = {}
        for v in var:
            if "=" not in v:
                print(f"Invalid --var '{v}', expected key=value")
                raise typer.Exit(1)
            k, val = v.split("=", 1)
            ctx[k] = val
        if not ctx.get("model_name"):
            ctx["model_name"] = file_name.title()
        output = template_registry.render(template=template, context=ctx, validate=True)
        path = Path(__file__).parent.parent / f"{file_name}.py"
        if path.exists():
            typer.confirm(f"File already exists at {path}, are you sure you want to overwrite it?", abort=True)
        if not dry_run:
            with open(path, "w") as f:
                f.write(output)
        else:
            print(f"Dry run enabled, will not write to {path}")
        print(f"\nRendered {template} with args: {ctx}: \n\n{output}")


@app.command(help="Auto hook up imports.")
def repair():
    lines: list[str] = []
    all_names: list[str] = []
    for f in sorted(MODELS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        tree = ast.parse(f.read_text())
        names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        for n in tree.body:
            if isinstance(n, ast.Assign):
                names += [t.id for t in n.targets if isinstance(t, ast.Name)]
        if not names:
            continue
        lines.append(f"from .{f.stem} import " + ", ".join(names))
        all_names += names

    body = "\n".join(lines)
    body += "\n\n__all__ = [" + ", ".join(f'"{n}"' for n in all_names) + "]\n"
    INIT_FILE.write_text(body)
