from pathlib import Path
import uuid
import inflection
from migrations.utils import migration_settings as m
from migrations.cli.app import migrations_database
from sqlalchemy import MetaData
from sqlacodegen.generators import SQLModelGenerator, DeclarativeGenerator
import ast
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from contextlib import contextmanager

MODELS_DIR = Path(__file__).parent.parent
BASES_DIR = MODELS_DIR / "bases"
if not BASES_DIR.exists():
    raise FileNotFoundError(f"Missing /bases folder at {BASES_DIR}")
VALIDATORS_DIR = MODELS_DIR / "validators"
if not VALIDATORS_DIR.exists():
    raise FileNotFoundError(f"Missing /validators folder at {VALIDATORS_DIR}")
INIT_FILE = MODELS_DIR / "__init__.py"
if not INIT_FILE.exists():
    raise FileNotFoundError(f"No __init__.py found at {INIT_FILE}")
SQL_DIR = Path(__file__).parent.parent.parent.parent.parent / "sql"
if not SQL_DIR.exists():
    raise FileNotFoundError(f"Missing '/sql' folder at {SQL_DIR}")

def ruff_format(code: str) -> str:
    p = subprocess.run(
        "uvx ruff format", shell=True, input=code, capture_output=True, text=True
    )
    return p.stdout if p.returncode == 0 else code


class Model():
    def __init__(self, class_def: ast.ClassDef):
        self.cls = class_def

    @property
    def fields(self) -> list[ast.AnnAssign]:
        return [
            s for s in self.cls.body
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
        ]

    def is_relationship(self, field: ast.AnnAssign) -> bool:
        return (
            isinstance(field.value, ast.Call)
            and isinstance(field.value.func, ast.Name)
            and field.value.func.id == "Relationship"
        )

    @staticmethod
    def is_tablename(s: ast.stmt):
        return (
            isinstance(s, ast.AnnAssign)
            and any(
                isinstance(t, ast.Name) 
                and t.id == "__tablename__" for t in s.targets
            )
        )

    @property
    def scalars(self):
        return [f for f in self.fields if not self.is_relationship(f)]

class SQLGenerator:
    def __init__(self, sqlmodel: bool = True, dry_run: bool = False):
        g = SQLModelGenerator if sqlmodel else DeclarativeGenerator
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
    def classes(self):
        return [n for n in self.tree.body if isinstance(n, ast.ClassDef)]

    def class_to_base(): ...
        """Removes 'table=True' and adds 'ABC'"""
    
    def class_to_validator(): ...
        """Changes to plain subclass of pydantic.BaseModel"""

    def class_to_typeddict(): ...
        """Changes to plain TypedDict"""

    def class_to_model(): ...
        """Imports the base and enables table=True for subclassing or adding methods"""

    @property
    def len_models(self) -> int:
        return len(self.classes)

    @property
    def header(self) -> str:
        return "\n".join(
            ast.get_source_segment(self.code, n) or ""
            for n in self.tree.body
            if isinstance(n, (ast.Import, ast.ImportFrom))
        )

    def write_files(self):
        for cls in self.classes:
            p = MODELS_DIR / f"{inflection.underscore(cls.name)}.py"
            src = f"{self.header}\n\n\n{ast.get_source_segment(self.code, cls)}\n"
            p.write_text(ruff_format(src))
