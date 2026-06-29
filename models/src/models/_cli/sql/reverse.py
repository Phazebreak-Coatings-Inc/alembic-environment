import ast
import importlib
from dataclasses import dataclass, field
from pathlib import Path

import inflection
from sqlalchemy import Column

from models._cli.sql.main import MODELS_DIR, Model

# The model generator (``models g``) goes SQL -> python. This goes the other way:
# it looks at what Alembic autogenerate actually sees (the live ``SQLModel.metadata``
# columns) and reconciles that against the SQL-derived ``base.py``. Anything present
# on the live model but missing from the SQL was *injected* in python -- typically a
# mixin column. Those injected fields are written back into ``model.py``, commented
# out, so the table file documents the columns alembic picked up without redeclaring
# them.

REVERSE_BEGIN = "# >>> reverse-generated (alembic) >>>"
REVERSE_END = "# <<< reverse-generated (alembic) <<<"
REVERSE_NOTE = (
    "# Columns below live on the model -- what Alembic autogenerate / SQLModel.metadata\n"
    "# sees -- but are NOT declared in ./models/sql. They're injected in python, e.g. via\n"
    "# a mixin. Shown commented-out, as documentation only; the mixin still owns them.\n"
)


def reverse_annotation(col: Column) -> str:
    """Best-effort python type annotation for a reflected/declared column."""
    try:
        pt = col.type.python_type
        ann = (
            pt.__qualname__
            if pt.__module__ == "builtins"
            else f"{pt.__module__}.{pt.__qualname__}"
        )
    except NotImplementedError:
        ann = "object"
    return f"Optional[{ann}]" if col.nullable else ann


def render_injected_field(col: Column) -> str:
    """A single commented-out ``Field`` line documenting one injected column."""
    ann = reverse_annotation(col)
    default = "default=None, " if col.nullable else ""
    sa = f'sa_column=Column("{col.name}", {col.type!r}, nullable={bool(col.nullable)})'
    return f"# {col.name}: {ann} = Field({default}{sa})  # reverse-generated from mixin"


def render_reverse_block(cols: list[Column]) -> str:
    body = "\n".join(render_injected_field(c) for c in cols)
    return f"{REVERSE_BEGIN}\n{REVERSE_NOTE}{body}\n{REVERSE_END}\n"


def strip_reverse_block(text: str) -> str:
    """Remove a previously written reverse block so writes stay idempotent."""
    if REVERSE_BEGIN not in text:
        return text.rstrip() + "\n"
    before = text.split(REVERSE_BEGIN, 1)[0].rstrip()
    tail = text.split(REVERSE_END, 1)
    after = tail[1].rstrip() if len(tail) > 1 else ""
    combined = f"{before}\n{after}" if after else before
    return combined.rstrip() + "\n"


@dataclass
class Reversed:
    directory: Path
    model_file: Path
    columns: list[Column] = field(default_factory=list)

    @property
    def name(self) -> str:
        return inflection.camelize(self.directory.name)


class ReverseGenerator:
    def __init__(self):
        self.results: list[Reversed] = [self._reverse(d) for d in self.model_dirs]

    @property
    def model_dirs(self) -> list[Path]:
        return [
            d
            for d in sorted(MODELS_DIR.iterdir())
            if d.is_dir()
            and not d.name.startswith(("_", "."))
            and (d / "base.py").exists()
            and (d / "model.py").exists()
        ]

    def _base_columns(self, directory: Path) -> set[str]:
        """The SQL-derived scalar column names, read straight from base.py."""
        tree = ast.parse((directory / "base.py").read_text())
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                m = Model(node)
                names.update(m.get_field_name(f) for f in m.scalars)
        return names

    def _concrete_class(self, directory: Path):
        """Import the table=True class so its columns register on the metadata."""
        mod = importlib.import_module(f"models.{directory.name}.model")
        cls = getattr(mod, inflection.camelize(directory.name), None)
        if cls is not None and hasattr(cls, "__table__"):
            return cls
        for value in vars(mod).values():
            if (
                isinstance(value, type)
                and hasattr(value, "__table__")
                and getattr(value, "__tablename__", None)
            ):
                return value
        raise LookupError(f"No table class found in models.{directory.name}.model")

    def _reverse(self, directory: Path) -> Reversed:
        base_cols = self._base_columns(directory)
        cls = self._concrete_class(directory)
        injected = [c for c in cls.__table__.columns if c.name not in base_cols]
        return Reversed(directory, directory / "model.py", injected)

    @property
    def injected_total(self) -> int:
        return sum(len(r.columns) for r in self.results)

    def preview(self) -> str:
        lines: list[str] = []
        for r in self.results:
            if not r.columns:
                continue
            lines.append(f"\n{r.name} ({r.model_file}):")
            lines += [f"  {render_injected_field(c)}" for c in r.columns]
        return "\n".join(lines) if lines else "No injected columns found."

    def write_files(self):
        for r in self.results:
            original = r.model_file.read_text()
            text = strip_reverse_block(original)
            if r.columns:
                text = f"{text.rstrip()}\n\n\n{render_reverse_block(r.columns)}"
            if text != original:
                r.model_file.write_text(text)
