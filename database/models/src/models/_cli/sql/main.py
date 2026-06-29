import ast
import copy
import subprocess
from pathlib import Path
from typing import Literal

import inflection
from migrations._cli.app import migrations_database
from migrations.utils import migration_settings as m
from sqlacodegen.generators import SQLModelGenerator
from sqlalchemy import MetaData
from sqlglot import exp
import sqlglot
from sqlalchemy import create_mock_engine

MODELS_DIR = Path(__file__).parent.parent.parent
INIT_FILE = MODELS_DIR / "__init__.py"
if not INIT_FILE.exists():
    raise FileNotFoundError(f"No __init__.py found at {INIT_FILE}")
SQL_DIR = Path(__file__).parent.parent.parent.parent.parent / "sql"
if not SQL_DIR.exists():
    raise FileNotFoundError(f"Missing '/sql' folder at {SQL_DIR}")


def ruff_format(code: str) -> str:
    p = subprocess.run(
        "uvx ruff format -", shell=True, input=code, capture_output=True, text=True
    )
    return p.stdout if p.returncode == 0 else code


FileKind = Literal["base", "typeddict", "validator", "model"]


class Model:
    def __init__(self, class_def: ast.ClassDef):
        self.cls = class_def

    @property
    def fields(self) -> list[ast.AnnAssign]:
        return [
            s
            for s in self.cls.body
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
        ]

    def is_relationship(self, field: ast.AnnAssign) -> bool:
        return (
            isinstance(field.value, ast.Call)
            and isinstance(field.value.func, ast.Name)
            and field.value.func.id == "Relationship"
        )

    @staticmethod
    def is_tablename(s: ast.stmt) -> bool:
        return isinstance(s, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__tablename__" for t in s.targets
        )

    @property
    def scalars(self):
        return [f for f in self.fields if not self.is_relationship(f)]

    def get_field_name(self, field: ast.AnnAssign) -> str:
        assert isinstance(field.target, ast.Name)
        return field.target.id

    def get_field_type(self, field: ast.AnnAssign):
        return ast.unparse(field.annotation)

    def is_optional(self, field: ast.AnnAssign) -> bool:
        t = self.get_field_type(field)
        return t.startswith("Optional[") or "| None" in t

    @property
    def name(self) -> str:
        return self.cls.name

    def class_to_base(self) -> str:
        """SQLModel base: the same class without table=True"""
        node = copy.deepcopy(self.cls)
        node.name = f"{self.name}Base"
        node.keywords = [k for k in node.keywords if k.arg != "table"]
        node.decorator_list = []
        return "from sqlmodel import SQLModel, Field, Relationship\n\n\n" + ast.unparse(
            node
        )

    def class_to_validator(self) -> str:
        """Plain pydantic.BaseModel."""
        lines = [f"class {self.name}Validator(BaseModel):"]
        for f in self.scalars:
            default = " = None" if self.is_optional(f) else ""
            lines.append(
                f"    {self.get_field_name(f)}: {self.get_field_type(f)}{default}"
            )
        return "from pydantic import BaseModel\n\n\n" + "\n".join(lines) + "\n"

    def class_to_typeddict(self) -> str:
        """Plain TypedDict."""
        lines = [f"class {self.name}Dict(TypedDict):"]
        for f in self.scalars:
            t = self.get_field_type(f)
            field = f"NotRequired[{t}]" if self.is_optional(f) else t
            lines.append(f"    {self.get_field_name(f)}: {field}")
        return (
            "from typing import NotRequired, TypedDict\n\n\n" + "\n".join(lines) + "\n"
        )

    def class_to_model(self) -> str:
        return (
            f"from .base import {self.name}Base\n\n\n"
            f"class {self.name}({self.name}Base, table=True):\n"
            f"    pass  # add methods here\n"
        )

    def class_to_init(self) -> str:
        names = [
            f"{self.name}Base",
            f"{self.name}Validator",
            f"{self.name}Dict",
            self.name,
        ]
        imports = (
            f"from .base import {self.name}Base\n"
            f"from .validator import {self.name}Validator\n"
            f"from .typeddict import {self.name}Dict\n"
            f"from .model import {self.name}\n"
        )
        exports = "__all__ = [" + ", ".join(f'"{n}"' for n in names) + "]\n"
        return imports + "\n" + exports

    def get_path(self, file: FileKind):
        return MODELS_DIR / inflection.underscore(self.name) / f"{file}.py"


class SQLGenerator:
    def __init__(self, dry_run: bool = False):
        g = SQLModelGenerator
        e = m.engine
        with migrations_database():
            with e.begin() as c:
                for f in self.files:
                    print(f"Applying {f.name}")
                    c.exec_driver_sql(f.read_text())

            md = MetaData()
            md.reflect(bind=e)
            self.code = ruff_format(g(md, e, options=[]).generate())

    @property
    def files(self) -> list[Path]:
        return list(SQL_DIR.glob("*.sql"))

    @property
    def tree(self) -> ast.Module:
        return ast.parse(self.code)

    @property
    def models(self):
        return [Model(n) for n in self.tree.body if isinstance(n, ast.ClassDef)]

    @property
    def len_models(self) -> int:
        return len(self.models)

    @property
    def header(self) -> str:
        return "\n".join(
            ast.get_source_segment(self.code, n) or ""
            for n in self.tree.body
            if isinstance(n, (ast.Import, ast.ImportFrom))
        )

    def write_files(self):
        for model in self.models:
            directory = model.get_path("model").parent
            directory.mkdir(parents=True, exist_ok=True)

            sources: dict[FileKind, str] = {
                "base": model.class_to_base(),
                "validator": model.class_to_validator(),
                "typeddict": model.class_to_typeddict(),
            }
            for kind, body in sources.items():
                model.get_path(kind).write_text(
                    ruff_format(f"{self.header}\n\n\n{body}")
                )

            model_path = model.get_path("model")
            if not model_path.exists():
                model_path.write_text(ruff_format(model.class_to_model()))

            (directory / "__init__.py").write_text(ruff_format(model.class_to_init()))

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

def get_sql_from_orm(metadata: MetaData):
    ddl = []
    engine = create_mock_engine("postgresql://", lambda sql, *a, **k: ddl.append(str(sql.compile(dialect=engine.dialect))))
    metadata.create_all(engine, checkfirst=False)
    return ddl

class SQLReverseGenerator:
    def __init__(self, metadata: MetaData):
        self.metadata = metadata

    @property
    def orm_creates(self) -> dict[str, exp.Create]:
        creates = {}
        for ddl in get_sql_from_orm(self.metadata):
            for c in get_creates(ddl):
                creates[create_to_table(c).name] = c
        return creates

    @property
    def sql_creates(self) -> dict[str, exp.Create]:
        creates = {}
        for f in SQL_DIR.glob("*.sql"):
            for c in get_creates(f.read_text()):
                creates[create_to_table(c).name] = c
        return creates

    def reverse_table(self, table: str) -> str:
        sql_cols = create_to_columns(self.sql_creates[table])
        sql_names = {c.name for c in sql_cols}
        orm_only = [
            c for c in create_to_columns(self.orm_creates[table])
            if c.name not in sql_names
        ]
        return render_create(table, sql_cols + merge_columns(sql_cols, orm_only))

    def generate(self) -> dict[str, str]:
        tables = self.sql_creates.keys() & self.orm_creates.keys()
        return {t: self.reverse_table(t) for t in tables}
