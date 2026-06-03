from pathlib import Path
from sqlmodel import SQLModel

MIGRATIONS_PROJECT_ROOT = Path(__file__).parent.parent.parents
APP_METADATA = SQLModel.metadata

from .utils import *
from .seeding import seed
