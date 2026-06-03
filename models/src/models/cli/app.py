from typer import Typer
import typer
from . import JINJA_ENV, TEMPLATES_DIR
import json
from typing import Annotated
from pathlib import Path

app = Typer()


@app.command(help=f"Create a model from a jinja2 template in {TEMPLATES_DIR}")
def generate_model(
    template: Annotated[
        str, typer.Argument(help="Template name, default is sqlmodel")
    ] = "sqlmodel",
    file_name: Annotated[
        str, typer.Argument(help="The name of your file")
    ] = "my_model",
    args: Annotated[str, typer.Option(help="JSON dict of template vars")] = "{}",
):
    ctx = json.loads(args)
    tmpl = JINJA_ENV.get_template(template)
    output = tmpl.render(**ctx)
    path = Path(__file__).parent.parent / f"{file_name}.py"
    with open(path, "w") as f:
        f.write(output)


@app.command()
def test(): ...
