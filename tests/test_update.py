import subprocess
from pathlib import Path

import pytest

from alembic_environment.config import ANSWERS_FILE
from alembic_environment.main import sh

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
def test_update(tmp_path):
    dst = tmp_path / "proj"
    prev = subprocess.check_output(
        ["git", "describe", "--tags", "--abbrev=0", "HEAD~1"],
        cwd=TEMPLATE_ROOT,
        text=True,
    ).strip()

    sh(
        f"copier copy {TEMPLATE_ROOT} {dst} --trust --vcs-ref={prev} --defaults --skip-tasks"
    )
    sh("git init", cwd=dst)
    sh("git add -A", cwd=dst)
    sh('git -c user.email=t@t -c user.name=t commit -m "init"', cwd=dst)
    sh(
        f"copier update -a {ANSWERS_FILE} --trust --vcs-ref=HEAD --defaults --conflict rej --skip-tasks",
        cwd=dst,
    )

    assert not list(dst.rglob("*.rej"))
