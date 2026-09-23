COPIER_REPO = "gh:Phazebreak-Coatings-Inc/alembic-environment"
"""The repo that copier should target."""

ANSWERS_FILE = ".alembic-environment-answers.yml"
"""The actual answers file that will be saved after user-interaction. 

If it has the same name as another copier-template project, your template will break.

Do not edit unless also changing the value in copier.yml.
"""

EXAMPLE_NAME = "example"
"""This is only used for the target dir where 'uv run python -m copier_template example ends up."""

EXAMPLE_PROJECT_NAME = "example_project"
"""This is what the pyproject.toml.[project].name will be after running 'uv run python -m copier_template example'"""

WORKSPACE: dict[str, str] = {
    "database_core": "database/database_core",
    "database_util": "database/database_util",
    "models": "database/models",
    "migrations": "database/migrations",
    "environments": "database/environments",
}
"""Workspace members to add to the target pyproject.

Maps package name to its path.

```python
{"some_dependency": "./some_dependency"}
```
"""

SCRIPTS: dict[str, str] = {}
"""Will add these scripts to the target pyproject, i.e.

```python
    {"my_script": "some_dependency.__main__:my_script"}
```
"""

PACKAGES = [
    "copier>=9.15.1",
    "inflection>=0.5.1",
    "pytest>=9.1.1",
    "tomlkit>=0.15.0",
    "typer>=0.26.6",
    "skylos>=4.29.0",
    "debugpy>=1.8.21",
    "alembic>=1.18.4",
    "sqlalchemy>=2.0.50",
    "sqlmodel>=0.0.38",
    "pytest-alembic>=0.12.1",
    "pydantic-settings>=2.14.1",
    "psycopg[binary]>=3.3.4",
    "ruff>=0.15.15",
    "sqlacodegen>=4.0.3",
    "sqlglot>=30.12.0",
]
"""The packages that should be added to the target pyproject."""


DATABASE_UTIL_SCRIPTS = {
    "models": "database_util.clis.models.app:app",
    "migrations": "database_util.clis.migrations.app:app",
    "environments": "database_util.clis.environments.app:app",
}
"""Scripts declared in database_util's pyproject so they install even when the target project is not packaged."""

EXAMPLE_PRESENT = ["alembic.ini", "database/models/tables.sql"]
