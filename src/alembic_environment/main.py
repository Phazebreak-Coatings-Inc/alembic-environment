from typer import Typer
import copier
import typer
import subprocess

app = Typer(pretty_exceptions_show_locals=False)

@app.command()
def init(dest = "."):
    copier.run_copy("gh:Phazebreak-Coatings-Inc/alembic-environment", dest)
    repair()

@app.command()
def update(abort: bool = False):
    match abort:
        case False:
            typer.confirm(
                "Are you sure you want to update? If you need to abort mid-update, it will trigger a 'git reset.' Make sure to save all uncommitted changes.",
                abort=True,
            )
            subprocess.run(
                "copier update --conflict inline",
                shell=True,
                check=True
            )
        case True:
            typer.confirm(
                "Are you sure you want to abort? This will trigger a 'git reset.'"
            )
            subprocess.run(
                "git reset",
                shell=True,
                check=True
            )
            subprocess.run(
                "git checkout .",
                shell=True,
                check=True
            )
            subprocess.run(
                "git clean -d -i",
                shell=True,
                check=True
            )
    repair()

@app.command()
def repair():
    ...
