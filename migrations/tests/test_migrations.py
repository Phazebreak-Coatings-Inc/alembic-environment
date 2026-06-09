from pytest_alembic.tests import (
    test_single_head_revision,
    test_upgrade,
    test_model_definitions_match_ddl,
    test_up_down_consistency,
)

# This exists so ruff doesn't remove it <3
tests = [
    test_single_head_revision,
    test_upgrade,
    test_model_definitions_match_ddl,
    test_up_down_consistency,
]
