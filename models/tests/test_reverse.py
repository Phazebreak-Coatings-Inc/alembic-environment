from sqlalchemy import Column, DateTime, Integer, String

from models._cli.sql.reverse import (
    REVERSE_BEGIN,
    REVERSE_END,
    render_injected_field,
    render_reverse_block,
    reverse_annotation,
    strip_reverse_block,
)

MODEL_PY = (
    "from .base import UsersBase\n\n\n"
    "class Users(UsersBase, table=True):\n"
    "    pass  # add methods here\n"
)


def test_reverse_annotation_wraps_optional_for_nullable():
    assert reverse_annotation(Column("a", Integer, nullable=False)) == "int"
    assert reverse_annotation(Column("a", Integer, nullable=True)) == "Optional[int]"
    assert (
        reverse_annotation(Column("created_at", DateTime(), nullable=True))
        == "Optional[datetime.datetime]"
    )


def test_render_injected_field_is_a_comment_noting_the_mixin():
    line = render_injected_field(Column("created_at", DateTime(), nullable=True))
    assert line.startswith("# created_at: Optional[datetime.datetime] = Field(")
    assert 'sa_column=Column("created_at"' in line
    assert line.endswith("# reverse-generated from mixin")


def test_round_trip_is_idempotent():
    cols = [
        Column("created_at", DateTime(), nullable=True),
        Column("tenant_id", String(50), nullable=False),
    ]
    block = render_reverse_block(cols)
    written = f"{MODEL_PY.rstrip()}\n\n\n{block}"

    assert REVERSE_BEGIN in written and REVERSE_END in written
    # Stripping the block restores the original user code exactly.
    assert strip_reverse_block(written) == MODEL_PY
    # Stripping a file that never had a block leaves it untouched.
    assert strip_reverse_block(MODEL_PY) == MODEL_PY


def test_rewrite_replaces_old_block_instead_of_stacking():
    first = f"{MODEL_PY.rstrip()}\n\n\n{render_reverse_block([Column('a', Integer)])}"
    refreshed = strip_reverse_block(first)
    second = f"{refreshed.rstrip()}\n\n\n{render_reverse_block([Column('b', Integer)])}"

    assert second.count(REVERSE_BEGIN) == 1
    assert "# a:" not in second
    assert "# b:" in second
