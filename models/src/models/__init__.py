from jinja2 import Environment, FileSystemLoader
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
if not TEMPLATES_DIR.exists():
    raise FileNotFoundError(f"Missing templates dir at {TEMPLATES_DIR}")

JINJA_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)

from .my_model import MyModel

__all__ = ["MyModel"]
