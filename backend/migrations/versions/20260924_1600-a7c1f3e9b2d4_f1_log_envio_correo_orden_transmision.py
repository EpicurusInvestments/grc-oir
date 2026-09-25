"""f1 log envio correo orden transmision

ADR-120 (petición del usuario) — "Enviar por correo" ahora también ofrece un envío
"bundle" fijo (PDF de Programados + Material a Transmitir) a TODOS los contactos
activos del afiliado, reusando `log_envio_correo_orden_estacion`:

- `tipo_pdf` gana un 4º valor permitido: 'orden_transmision' (el CHECK constraint se
  recrea con los 4 valores).
- `destinatario_email` se ensancha de 320 a 2000 caracteres: este envío puede ir a
  VARIOS contactos, guardados como lista separada por coma en la misma columna.

SQLite no soporta `ALTER ... DROP CONSTRAINT`/ensanchar columna de forma directa — se
usa `batch_alter_table` (mismo criterio que `55d7f36d93fd`, skill migraciones-sqlserver).

Revision ID: a7c1f3e9b2d4
Revises: 0b643d77d4cc
Create Date: 2026-09-24 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a7c1f3e9b2d4'
down_revision: str | None = '0b643d77d4cc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = 'log_envio_correo_orden_estacion'
_CHECK = 'ck_log_envio_correo_oe_tipo_pdf'
_VALORES_NUEVOS = "tipo_pdf IN ('servicio', 'programados', 'reales', 'orden_transmision')"
_VALORES_VIEJOS = "tipo_pdf IN ('servicio', 'programados', 'reales')"


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.alter_column(
                'destinatario_email',
                existing_type=sa.Unicode(length=320),
                type_=sa.Unicode(length=2000),
                existing_nullable=False,
            )
            batch.drop_constraint(_CHECK, type_='check')
            batch.create_check_constraint(_CHECK, _VALORES_NUEVOS)
    else:
        op.alter_column(
            _TABLA,
            'destinatario_email',
            existing_type=sa.Unicode(length=320),
            type_=sa.Unicode(length=2000),
            existing_nullable=False,
        )
        op.drop_constraint(_CHECK, _TABLA, type_='check')
        op.create_check_constraint(_CHECK, _TABLA, _VALORES_NUEVOS)


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.drop_constraint(_CHECK, type_='check')
            batch.create_check_constraint(_CHECK, _VALORES_VIEJOS)
            batch.alter_column(
                'destinatario_email',
                existing_type=sa.Unicode(length=2000),
                type_=sa.Unicode(length=320),
                existing_nullable=False,
            )
    else:
        op.drop_constraint(_CHECK, _TABLA, type_='check')
        op.create_check_constraint(_CHECK, _TABLA, _VALORES_VIEJOS)
        op.alter_column(
            _TABLA,
            'destinatario_email',
            existing_type=sa.Unicode(length=2000),
            type_=sa.Unicode(length=320),
            existing_nullable=False,
        )
