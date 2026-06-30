"""Entorno de Alembic.

La URL de conexión se toma de `settings.sqlalchemy_url` (construida desde el `.env`),
nunca del `alembic.ini`, para no versionar credenciales.

`target_metadata = Base.metadata` para que `--autogenerate` detecte los modelos. En
F0-00 todavía no hay entidades; desde F0-01 se importan aquí los modelos para que sus
tablas entren al metadata.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.core.config import settings
from app.core.db import Base
from sqlalchemy import engine_from_config, pool

# TODO(F0-01+): importar los modelos para que Base.metadata los conozca, p.ej.:
#   from app.modules.catalogos import plaza  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
