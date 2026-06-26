from sqlmodel import Session
from pathlib import Path
from typing import Callable, get_type_hints
from migrations.utils import (
    ValidDatabaseEnvironments,
    validate_database_environment,
    get_database_setting,
)
from collections import defaultdict
import inflection

SEEDS_DIRECTORY = Path(__file__).parent.parent.parent / "seeds"

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

def execute_seeds(env: ValidDatabaseEnvironments):
    env = validate_database_environment(env)
    with Session(get_database_setting(env).engine) as s:
        for fn in seed_registry.get_seeds(env):
            try:
                fn(s)
            except Exception as e:
                raise SeedingException(f"Seeding failed for {fn.__name__}: {e}") from e
        s.commit()


SEED_TEMPLATE = """
from models import *
from sqlmodel import Session
from migrations import seed, {env}

@seed({env})
def {name}(session: Session) -> None:
    ...
"""

SEED_TEST_TEMPLATE = """
from migrations


"""

def generate_seed_file(name: str, env: ValidDatabaseEnvironments, w: bool = True):
    n = inflection.underscore(name)
    p = SEEDS_DIRECTORY / f"{n}.py"
    if w:
        p.write_text(t := SEED_TEMPLATE.format(
            env=env,
            name=n
        ))
    print(f"Generated new seed file to {p}: \n{t}")

#def generate_seed_test() ...

#def repair_seeds() ...
