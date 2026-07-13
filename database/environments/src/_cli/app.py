import typer
from typing import Literal, Annotated, Any
from pydantic import BeforeValidator, validate_call

app = typer.Typer()


@app.command(help="Starts the database cluster for a specific environment.")
def start(): ...


@app.command(help="Resets to project defaults for database clusters.")
def reset(): ...
