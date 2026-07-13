from pathlib import Path

DIR_DATABASE = Path(__file__).parent.parent.parent
WS_ENVIRONMENTS = DIR_DATABASE / "environments"
WS_MIGRATIONS = DIR_DATABASE / "migrations"
WS_MODELS = DIR_DATABASE / "models"
DIR_SQL = WS_MODELS / "sql"
PKG_MODELS = WS_MODELS / "src" / "models"
PKG_MIGRATIONS = WS_MIGRATIONS / "src" / "migrations"
PKG_ENVIRONMENTS = WS_ENVIRONMENTS / "src" / "environments"
DIR_SEEDS = PKG_MIGRATIONS / "seeds"
INIT_MODELS = PKG_MODELS / "__init__.py"
