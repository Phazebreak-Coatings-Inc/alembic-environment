from typer import Typer
import typer
from models.templates import template_registry
from models.templates.main import TEMPLATES_DIR
from typing import Annotated
from pathlib import Path

app = Typer()


@app.command(help=f"Create a model from a jinja2 template in {TEMPLATES_DIR}")
def generate_model(
    template: Annotated[str, typer.Argument(help="Template name, default is sqlmodel")] = "",
    file_name: Annotated[str, typer.Argument(help="The name of your file")] = "",
    var: Annotated[list[str], typer.Option("--var", "-v", help="key=value, repeatable")] = list(),
    dry_run: Annotated[
        bool,
        typer.Option(
            "-dr", "--dry-run", help="Generate the model without writing to disk."
        ),
    ] = False,
):
    ctx = dict(v.split("=", 1) for v in var)
    output = template_registry.render(template=template, context=ctx, validate=True)
    path = Path(__file__).parent.parent / f"{file_name}.py"
    if not dry_run:
        with open(path, "w") as f:
            f.write(output)

@app.command(help="Repair the models dir, auto hook up imports, etc.")
def repair():
    ...
