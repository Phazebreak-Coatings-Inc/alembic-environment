from collections import defaultdict
import typer
from typing import Callable, get_type_hints

from pydantic import validate_call
import inflection
from sqlmodel import Session

from . import DatabaseEnvironment, get_database_setting, run_steps, DIR_SEEDS

SeedFunction = Callable[[Session], None]
SeedRegistry = dict[DatabaseEnvironment, list[SeedFunction]]


class SeedingException(Exception): ...


class Seed:
    __seeds__: SeedRegistry = defaultdict(list)

    @classmethod
    @validate_call
    def seed(cls, env: DatabaseEnvironment):
        def dec(fn) -> SeedFunction:
            if not (sesh := get_type_hints(fn).get("session", None)):
                raise SeedingException(
                    f"session must be passed as a type hint in fn {fn.__name__}"
                )
            if not (isinstance(sesh, type) and issubclass(sesh, Session)):
                raise SeedingException(
                    f"`session` of {fn.__name__} must be a sqlmodel.Session subclass"
                )
            cls.__seeds__[env].append(fn)
            return fn

        return dec

    @validate_call
    def count_seeds(self, env: DatabaseEnvironment) -> int:
        return len(self.__seeds__[env])

    @validate_call
    def get_seeds(self, env: DatabaseEnvironment) -> list[SeedFunction]:
        return self.__seeds__[env]


seed_registry = Seed()
seed = seed_registry.seed


@validate_call
def execute_seeds(
    env: DatabaseEnvironment, dry_run: bool = False, confirm: bool = True
):
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
            print(
                f"Successfully ran and rolled-back {len(fns)} seeding functions in '{env}' environment."
            )
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


@validate_call
def generate_seed_file(env: DatabaseEnvironment, name: str, dry_run: bool = False):
    n = inflection.underscore(name)
    p = DIR_SEEDS / f"{n}.py"
    if p.exists():
        typer.confirm(
            f"{p.name} already exists, are you sure you want to overwrite it?",
            abort=True,
        )
    else:
        p.touch()

    t = SEED_TEMPLATE.format(env=env, name=n)

    if dry_run:
        print(f"Would write new seed file to {p}: \n\n{t}\n")

    p.write_text(t)
    print(f"Wrote new seed file to {p}: \n\n{t}\n")
    return
