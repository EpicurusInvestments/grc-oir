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

# Importar los modelos para que Base.metadata conozca sus tablas (autogenerate).
# F0-01: operativos · F0-02: tarifa · F0-03: comerciales + bitácora de auditoría.
from app.core import audit  # noqa: F401  (modelo LogCambioParametro)
from app.core.config import settings
from app.core.db import Base
from app.modules.catalogos import (  # noqa: F401
    afiliado,
    agencia,
    anunciante,
    estacion,
    plaza,
    tarifa,
)
from sqlalchemy import create_engine, pool

config = context.config

# La URL NO se pasa por `config.set_main_option`: contiene el odbc_connect URL-encodeado
# (con '%'), y configparser lo interpretaría como sintaxis de interpolación y fallaría.
# Se usa `settings.sqlalchemy_url` directamente al crear el engine / configurar el contexto.

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
    connectable = create_engine(
        settings.sqlalchemy_url, poolclass=pool.NullPool, future=True
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
