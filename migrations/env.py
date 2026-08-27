from __future__ import with_statement

import os
import sys
from pathlib import Path

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model import db

config = context.config

# S-38: without this, alembic.ini's [logger_alembic] section is never applied and every
# migration runs silently -- success and no-op are indistinguishable from the output,
# including during a deploy. alembic.ini has carried the full logging config all along;
# this line is what was missing.
#
# The path has to be resolved rather than trusted. The two entry points disagree:
#
#   alembic ...        -> config_file_name = "alembic.ini"            (repo root, exists)
#   flask db upgrade   -> config_file_name = "migrations/alembic.ini" (does NOT exist)
#
# Flask-Migrate hardcodes `Config(os.path.join(directory, 'alembic.ini'))`, and this
# project keeps its ini at the repo root instead. The name is therefore non-None but
# points at nothing; `fileConfig` on a missing file builds an empty parser and dies with
# `KeyError: 'formatters'`. That took out `flask db upgrade` entirely -- including the
# migration step of every deploy -- from 2026-08-19, the same commit that added this
# line and the company.domain migration it was meant to log. Hence a migration that
# existed in the repo for a week but had never been applied anywhere.
def _logging_config_path() -> "str | None":
    """Return an alembic ini that actually exists, preferring the invoker's own."""
    candidates = [config.config_file_name, str(PROJECT_ROOT / "alembic.ini")]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


_ini_path = _logging_config_path()
if _ini_path is not None:
    fileConfig(_ini_path)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def get_metadata():
    return db.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=get_metadata())

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
