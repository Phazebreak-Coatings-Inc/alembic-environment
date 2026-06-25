"""initial

Revision ID: 546a0bb854f0
Revises:
Create Date: 2026-06-09 14:41:15.551805

"""

from typing import Sequence, Union


revision: str = "546a0bb854f0"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(): ...


def downgrade(): ...
