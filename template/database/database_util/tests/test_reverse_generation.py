import pytest
from database_util import utils
from database_util.utils import SQLReverseGenerator
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKeyConstraint,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    Uuid,
    text,
)

TIME_OFF_SQL = """
CREATE TABLE employee (
  id UUID PRIMARY KEY
);

CREATE TABLE time_off (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID NOT NULL REFERENCES employee (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  hours DECIMAL(5, 2) NOT NULL CHECK (hours > 0),
  status VARCHAR(20) NOT NULL DEFAULT 'Waiting'
    CHECK (status IN ('Approved', 'Denied', 'Waiting')),
  CHECK (end_date >= start_date)
);
"""


def reflected_time_off(*extra) -> MetaData:
    md = MetaData()
    Table("employee", md, Column("id", Uuid, primary_key=True))
    Table(
        "time_off",
        md,
        Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
        Column("employee_id", Uuid, nullable=False),
        Column("title", Text, nullable=False),
        Column("start_date", Date, nullable=False),
        Column("end_date", Date, nullable=False),
        Column("hours", Numeric(5, 2), nullable=False),
        Column(
            "status",
            String(20),
            nullable=False,
            server_default=text("'Waiting'::character varying"),
        ),
        CheckConstraint("end_date >= start_date", name="time_off_check"),
        CheckConstraint("hours > 0::numeric", name="time_off_hours_check"),
        CheckConstraint(
            "status::text = ANY (ARRAY['Approved'::character varying, "
            "'Denied'::character varying, 'Waiting'::character varying]::text[])",
            name="time_off_status_check",
        ),
        ForeignKeyConstraint(
            ["employee_id"],
            ["employee.id"],
            ondelete="CASCADE",
            name="time_off_employee_id_fkey",
        ),
        *extra,
    )
    return md


@pytest.fixture
def tables_sql(tmp_path, monkeypatch):
    path = tmp_path / "tables.sql"
    path.write_text(TIME_OFF_SQL)
    monkeypatch.setattr(utils, "TABLES_SQL", path)
    return path


def test_rg_skips_checks_postgres_rewrote(tables_sql):
    out = SQLReverseGenerator(reflected_time_off()).reverse_table("time_off")
    assert "CONSTRAINT" not in out
    assert out.count("CHECK") == 3


def test_rg_adds_model_only_check(tables_sql):
    md = reflected_time_off(CheckConstraint("hours < 100", name="time_off_hours_max"))
    out = SQLReverseGenerator(md).reverse_table("time_off")
    assert "CONSTRAINT time_off_hours_max CHECK (hours < 100)" in out
    assert out.count("CONSTRAINT") == 1


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("CREATE TABLE t (a INT CHECK (a > 0))", {"t_a_check"}),
        ("CREATE TABLE t (a INT, b INT, CHECK (a > b))", {"t_check"}),
        ("CREATE TABLE t (a INT, CHECK (a > 0))", {"t_a_check"}),
        (
            "CREATE TABLE t (a INT CHECK (a > 0) CHECK (a < 9))",
            {"t_a_check", "t_a_check1"},
        ),
        (
            "CREATE TABLE t (a INT CONSTRAINT pos CHECK (a > 0), "
            "CONSTRAINT u UNIQUE (a))",
            {"pos", "u"},
        ),
    ],
)
def test_constraint_names_match_postgres(sql, expected):
    create = utils.get_creates(sql)[0]
    assert utils.constraint_names("t", create) == expected
