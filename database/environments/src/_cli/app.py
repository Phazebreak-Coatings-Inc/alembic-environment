import typer
from typing import Literal, Annotated, Any
from pydantic import BeforeValidator, validate_call

app = typer.Typer()

@validate_call
def is_valid_environment(env: str) -> "EnvironmentName": ...

EnvironmentType = Literal["docker", "terraform"]
TerraformType = Literal["azure"]
EnvironmentName = Annotated[str, BeforeValidator(is_valid_environment)]
EnvironmentTypeArgument = Annotated[EnvironmentName, typer.Option(help="The environment you want to select. Defaults are dev, prod, and staging")]

def get_environments(): ...

def get_environment_env(env: EnvironmentName) -> dict[str, Any]: ...

@app.command(help="Generates a custom database environment")
def g(typ: EnvironmentType): ...

@app.command(help="Validates env files at the correct place with the correct keys")
def validate(typ: EnvironmentType, all: bool): ...

@app.command()
def up(): ...

@app.command()
def defaults(repair: bool, reset: bool):
    ...
