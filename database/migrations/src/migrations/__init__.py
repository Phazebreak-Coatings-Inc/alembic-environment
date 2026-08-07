from pathlib import Path
from sqlmodel import SQLModel
from .seeds import *
from .backfills import *

APP_METADATA = SQLModel.metadata
