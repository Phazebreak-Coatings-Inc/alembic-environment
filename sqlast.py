from sqlglot import Expr, parse
from sqlglot import expressions as exp
from pathlib import Path
import sqlmodel
import sqlglot
from sqlalchemy import MetaData

sql = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
)
"""

DIALECT = "postgres"

class SQLParseError(Exception): ...

def get_creates(sql: str) -> list[exp.Create]:
    return [s for s in sqlglot.parse(sql) if isinstance(s, exp.Create)]

def create_to_columns(create: exp.Create) -> list[exp.ColumnDef]:
    return list(create.find_all(exp.ColumnDef))

def create_to_table(create: exp.Create) -> exp.Table:
    return create.this.find(exp.Table)

class SQLMergeError(Exception): ...

def as_comment(col: exp.ColumnDef) -> exp.ColumnDef:
    setattr(col, "_commented", True)
    return col

def is_comment(col: exp.ColumnDef) -> bool:
    return getattr(col, "_commented", False)

def merge_columns(
    c1: list[exp.ColumnDef],
    c2: list[exp.ColumnDef],
    comment: bool = True,
):
    names = {c.name for c in c1}
    merged = []
    for col in c2:
        if col.name in names:
            raise SQLMergeError(f"Column '{col.name}' is already defined") 
        merged.append(as_comment(col) if comment else col)
    return merged 

def render_create(table: str, cols: list[exp.ColumnDef]) -> str:
    real = [c for c in cols if not is_comment(c)]
    commented = [c for c in cols if is_comment(c)]
    body = ",\n  ".join(c.sql(dialect=DIALECT) for c in real)
    out = f"CREATE TABLE {table} (\n  {body}"
    if commented:
        out += "\n  " + "\n  ".join("-- " + c.sql(dialect=DIALECT) for c in commented)
    return out + "\n)"

MyMetadata = sqlmodel.MetaData()

class Users(sqlmodel.SQLModel, table=True):
    metadata = MyMetadata
    id: int  = sqlmodel.Field(primary_key = True)

from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from sqlalchemy.engine import create_mock_engine

def get_sql_from_orm(metadata: MetaData):
    ddl = []
    engine = create_mock_engine("postgresql://", lambda sql, *a, **k: ddl.append(str(sql.compile(dialect=engine.dialect))))
    metadata.create_all(engine, checkfirst=False)
    return ddl

print(get_sql_from_orm(MyMetadata))
