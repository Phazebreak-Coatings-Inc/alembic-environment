from collections import defaultdict
import typer
from pathlib import Path
from typing import Callable, get_type_hints

import inflection
from sqlmodel import Session

from migrations.utils import (
    ValidDatabaseEnvironments,
    get_database_setting,
    validate_database_environment,
    run_steps
)

SEEDS_DIRECTORY = Path(__file__).parent.parent.parent / "seeds"
if not SEEDS_DIRECTORY.exists():
    raise FileNotFoundError(f"Couldn't find seeds direcotry at {SEEDS_DIRECTORY}!")

SeedFunction = Callable[[Session], None]
SeedRegistry = dict[ValidDatabaseEnvironments, list[SeedFunction]]


class SeedingException(Exception): ...


class Seed:
    __seeds__: SeedRegistry = defaultdict(list)

    @classmethod
    def seed(cls, env: ValidDatabaseEnvironments):
        def dec(fn) -> SeedFunction:
            if not (sesh := get_type_hints(fn).get("session", None)):
                raise SeedingException(
                    f"session must be passed as a type hint in fn {fn.__name__}"
                )
            if not (isinstance(sesh, type) and issubclass(sesh, Session)):
                raise SeedingException(
                    f"`session` of {fn.__name__} must be a sqlmodel.Session subclass"
                )
            cls.__seeds__[validate_database_environment(env)].append(fn)
            return fn

        return dec

    def count_seeds(self, env: ValidDatabaseEnvironments) -> int:
        return len(self.__seeds__[(validate_database_environment(env))])

    def get_seeds(self, env: ValidDatabaseEnvironments) -> list[SeedFunction]:
        return self.__seeds__[(validate_database_environment(env))]


seed_registry = Seed()
seed = seed_registry.seed


def execute_seeds(
    env: ValidDatabaseEnvironments, 
    dry_run: bool = False,
    confirm: bool = True
):
    env = validate_database_environment(env)
    errors: list[tuple[str, Exception]] = []

    with Session(get_database_setting(env).engine) as s:
        def make_step(fn):
            def step():
                try:
                    with s.begin_nested():
                        fn(s)
                except Exception as e:
                    errors.append((fn.__name__, e))
            return step

        fns = [make_step(fn) for fn in seed_registry.get_seeds(env)]

        if len(fns) == 0:
            print(f"Found 0 seeds for environment '{env}'...")
            raise typer.Abort()

        if confirm and not dry_run:
            typer.confirm(
                f"This action will run {seed_registry.count_seeds(env)} functions on environment '{env},' Are you sure you want to proceed?",
                abort=True,
            )

        run_steps(
            label=f"Seeding '{env}' environment",
        )

        if errors:
            s.rollback()
            details = "\n".join(f"  {name}: {e}" for name, e in errors)
            raise SeedingException(f"{len(errors)} seed(s) failed:\n{details}")
        if dry_run:
            s.rollback()
            print(f"Successfully ran and rolled-back {len(fns)} seeding functions in '{env}' environment.")
            return

        print(f"Successfully ran {len(fns)} seeding functions in '{env}' environment.")
        s.commit()


SEED_TEMPLATE = """from models import *
from sqlmodel import Session
from migrations import seed, {env}

@seed({env})
def {name}(session: Session) -> None:
    ...
"""

def generate_seed_file(env: ValidDatabaseEnvironments, name: str, dry_run: bool = False):
    n = inflection.underscore(name)
    p = SEEDS_DIRECTORY / f"{n}.py"
    if p.exists():
        typer.confirm(f"{p.name} already exists, are you sure you want to overwrite it?", abort=True)
    else:
        p.touch()

    t = SEED_TEMPLATE.format(env=env, name=n)

    if dry_run:
        print(f"Would write new seed file to {p}: \n\n{t}\n")

    p.write_text(t)
    print(f"Wrote new seed file to {p}: \n\n{t}\n")
    return

