import tomlkit
from alembic_environment.main import add_workspaces 

def test_add_workspaces_fresh():
    doc = tomlkit.parse("")
    out = add_workspaces(doc, ["models", "migrations"])
    ws = out["tool"]["uv"]["workspace"]["members"]
    assert list(ws) == ["models", "migrations"]
    src = out["tool"]["uv"]["sources"]
    assert src["models"]["workspace"] is True

def test_add_workspaces_merges_existing():
    doc = tomlkit.parse(
        '[tool.uv.workspace]\nmembers = ["models"]\n'
    )
    out = add_workspaces(doc, ["models", "migrations"])
    assert list(out["tool"]["uv"]["workspace"]["members"]) == ["models", "migrations"]
