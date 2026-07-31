import typer
from typing import Annotated

from ...utils import EnvArg, get_database_setting, e

app = typer.Typer()


@app.command(help="Starts the database cluster for a specific environment.")
@e
def up(env: EnvArg):
    s = get_database_setting(env)
    s.up()

@app.command(help="Turns off the database cluster for a specific environment.")
@e
def down(
    env: EnvArg, destroy: Annotated[bool, typer.Option("--destroy", "-d")] = False
):
    s = get_database_setting(env)
    s.down() if not destroy else s.destroy()


@app.command(help="Tests a database environment.")
@e
def test(
    env: EnvArg,
):
    s = get_database_setting(env)
    s.test()


@app.command(help="Ping a database environment.")
@e
def ping(env: EnvArg):
    s = get_database_setting(env)
    s.ping(verbose=True)
