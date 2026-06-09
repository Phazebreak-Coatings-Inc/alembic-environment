from pathlib import Path
from typing import Literal
import uuid
import inflection
from migrations.utils import migration_settings as m
from migrations._cli.app import migrations_database
from sqlalchemy import MetaData
from sqlacodegen.generators import SQLModelGenerator, DeclarativeGenerator
import ast
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from contextlib import contextmanager
import copy

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
        names = [f"{self.name}Base", f"{self.name}Validator", f"{self.name}Dict", self.name]
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
                model.get_path(kind).write_text(ruff_format(f"{self.header}\n\n\n{body}"))

            model_path = model.get_path("model")
            if not model_path.exists():
                model_path.write_text(ruff_format(model.class_to_model()))

            (directory / "__init__.py").write_text(ruff_format(model.class_to_init()))
