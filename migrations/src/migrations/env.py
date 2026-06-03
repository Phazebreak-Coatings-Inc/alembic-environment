from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
import os
from migrations.utils import (
    migration_settings,
    get_database_setting,
    validate_database_environment,
)
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from migrations.utils import APP_METADATA

target_metadata = APP_METADATA


def _resolve_url() -> str:
    if env := os.environ.get("ALEMBIC_ENV"):
        return get_database_setting(validate_database_environment(env)).database_url
    return migration_settings.database_url


def process_revision_directives(context, revision, directives):
    if getattr(context.config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []


def run_migrations_offline() -> None:
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection", None)

    if connectable is None:
        section = context.config.get_section(context.config.config_ini_section) or {}
        section["sqlalchemy.url"] = _resolve_url()
        connectable = engine_from_config(
            section,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            process_revision_directives=process_revision_directives,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
