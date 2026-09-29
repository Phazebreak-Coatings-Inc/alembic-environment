import re
from pathlib import Path

import pytest
import tomlkit
import yaml

from alembic_environment.config import (
    DATABASE_UTIL_SCRIPTS,
    DEPENDENCIES,
    PACKAGES,
    WORKSPACE,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
PROD = TEMPLATE / "database" / "database_environments" / "clusters" / "prod"
DEV_TOOLS = {"pytest", "ruff", "copier", "sqlacodegen", "pytest-alembic", "typer"}


def requirement_name(req: str) -> str:
    return re.split(r"[\s\[<>=!~;@]", req, maxsplit=1)[0].lower()


@pytest.mark.parametrize("name,path", WORKSPACE.items())
def test_workspace_member_exists(name, path):
    assert (TEMPLATE / path / "src" / name / "__init__.py").is_file()


def test_database_util_declares_scripts():
    util = tomlkit.parse(
        (TEMPLATE / WORKSPACE["database_util"] / "pyproject.toml").read_text()
    )
    assert dict(util["project"]["scripts"]) == DATABASE_UTIL_SCRIPTS


def test_dev_tools_are_not_runtime_dependencies():
    assert not {requirement_name(d) for d in DEPENDENCIES} & DEV_TOOLS
    assert DEV_TOOLS <= {requirement_name(p) for p in PACKAGES}


def test_only_root_gitignore_is_excluded():
    excludes = yaml.safe_load((ROOT / "copier.yml").read_text())["_exclude"]
    assert ".gitignore" not in excludes
    assert "/.gitignore" in excludes
    ignored = (PROD.parent / ".gitignore").read_text().split()
    assert ".terraform" in ignored


def test_module_sources_exist_and_are_pinned():
    sources = re.findall(r'source\s*=\s*"(git::[^"]+)"', (PROD / "main.tf").read_text())
    assert len(sources) == 4
    for source in sources:
        match = re.search(r"//(terraform/modules/[^?]+)\?ref=(.+)$", source)
        assert match, source
        module, ref = match.groups()
        assert (ROOT / module / "main.tf").is_file(), module
        assert ref != "terraform-pattern", source
