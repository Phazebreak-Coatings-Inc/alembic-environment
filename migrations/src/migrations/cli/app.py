import typer
from typer import Typer
import subprocess
from ..utils import migration_settings as m, validate_database_environment, ValidDatabaseEnvironments
from typing import Annotated
from ..seeding import execute_seeds

app = Typer()

@app.command(help="Automatically test the alembic revisions generated.")
def test():
    subprocess.run(
        "pytest",
        shell=True,
    )

@app.command(help="Start up the migrations database for autogenerating alembic revisions.")
def up():
    subprocess.run(
        "docker pull postgres",
        shell=True,
        check=True
    )
    subprocess.run(
        f"docker run -d --name {m.database_name} -e POSTGRES_USERNAME={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p {m.database_port}:{m.database_port} --rm",
        shell=True,
        check=True
    )
    subprocess.run(
        f"until docker exec {m.database_name} pg_isready -U {m.database_username}; "
        f"do sleep 0.5; done",
        shell=True, 
        check=True,
    )

@app.command(help="Shut down the migrations database.")
def down():
    subprocess.run(
        f"docker rm -f {m.database_name}", 
        shell=True,
        check=True
    )

@app.command(help="Seed the database with anything decorated with 'seed'.")
def seed(env: Annotated[ValidDatabaseEnvironments, typer.Argument(help="Choose which environment to seed for.")]):
    execute_seeds(env)
