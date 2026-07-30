import typer
from typing import Annotated

from ...utils import EnvArg, get_database_setting

app = typer.Typer()


@app.command(help="Starts the database cluster for a specific environment.")
def up(env: EnvArg):
    s = get_database_setting(env)
    s.up()


@app.command(help="Turns off the database cluster for a specific environment.")
def down(
    env: EnvArg, destroy: Annotated[bool, typer.Option("--destroy", "-d")] = False
):
    s = get_database_setting(env)
    s.down() if not destroy else s.destroy()


@app.command(help="Tests a database environment.")
def test(
    env: EnvArg,
):
    s = get_database_setting(env)
    s.test()


@app.command(help="Ping a database environment.")
def ping(env: EnvArg):
    s = get_database_setting(env)
    s.ping()
