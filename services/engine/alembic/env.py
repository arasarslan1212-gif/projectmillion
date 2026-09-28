"""Alembic environment: the database URL comes from DATABASE_URL (engine settings)."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from engine.db.models import Base
from engine.settings import get_settings

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
