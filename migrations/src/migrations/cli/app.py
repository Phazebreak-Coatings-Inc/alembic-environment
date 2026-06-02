from typer import Typer
import subprocess
import shlex
from ..utils import MigrationGeneratorSettings

app = Typer()


@app.command()
def test():
    subprocess.run(
        "pytest",
        shell=True,
        check=True
    )

@app.command()
def migrations_database_up():
    m = MigrationGeneratorSettings()
    subprocess.run(
        "docker pull postgres",
        shell=True,
        check=True
    )
    subprocess.run(
        f"docker run -d --name {m.database_name} -e POSTGRES_USERNAME={m.database_username} -e POSTGRES_PASSWORD={m.database_password} -e POSTGRES_DB=migrations -p 5432:5432 --rm",
        shell=True,
        check=True
    )

@app.command()
def migrations_database_down():
    m = MigrationGeneratorSettings()
    subprocess.run(
        f"docker rm -f {m.database_name}", 
        shell=True,
        check=True
    )
