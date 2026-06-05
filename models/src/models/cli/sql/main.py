from pathlib import Path
import inflection
from migrations.utils import migration_settings as m
from migrations.cli.app import migrations_database
from sqlalchemy import MetaData
from sqlacodegen.generators import SQLModelGenerator, DeclarativeGenerator
from typing import Any
import ast


MODELS_DIR = Path(__file__).parent.parent
INIT_FILE = MODELS_DIR / "__init__.py"
if not INIT_FILE.exists():
    raise FileNotFoundError(f"No __init__.py found at {INIT_FILE}")
SQL_DIR = Path(__file__).parent.parent.parent.parent.parent / "sql"
if not SQL_DIR.exists():
    raise FileNotFoundError(f"Missing '/sql' folder at {SQL_DIR}")

class SQLGenerator():
    code: str

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
            self.code = g(md, e, options=[]).generate()

    @property
    def files(self) -> list[Path]:
        return list(SQL_DIR.glob('*.sql'))
    
    @property
    def tree(self) -> ast.Module:
        return ast.parse(self.code)

    @property
    def classes(self):
        return [n for n in self.tree.body if isinstance(n, ast.ClassDef)]
    
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
        out = MODELS_DIR / "src" / "models"
        for cls in self.classes:
            src = ast.get_source_segment(self.code, cls)
            p = out / f"{inflection.underscore(cls.name)}.py"
            p.write_text(f"{self.header}\n\n\n{src}\n")
     
