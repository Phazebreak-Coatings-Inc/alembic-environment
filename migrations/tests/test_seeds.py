import pytest
from migrations._cli.seeding import seed_registry
from sqlmodel import Session

@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_seeds_run(env, alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to("head")        
    for fn in seed_registry.get_seeds(env):
        with Session(alembic_engine) as s:
            fn(s); s.rollback() 
