"""f2 backfill factura_agencia_orden

Migración de DATOS: copia cada `FacturaAgencia` existente (con su `orden_id`/
`porcentaje_comision_agencia`/`comision_agencia` de la cabecera, ADR-079) a UNA fila de
`FacturaAgenciaOrden` (ADR nuevo, `b7f3a1c9d2e4`), antes de que el siguiente paso
(`f2a9c5d7e1b8`) elimine esas columnas de la cabecera. `COALESCE(..., 0)` para
`porcentaje_comision_agencia`/`comision_agencia`: aunque ambas eran nullable antes, la
app siempre las llenaba al capturar (se sugería el default del catálogo); se cubre el
caso NULL por seguridad, no porque se esperen filas así en producción.

El id de cada fila nueva se genera en Python (`uuid.uuid4()`), no en SQL: SQLite no
tiene función de UUID y la de SQL Server (`NEWID()`) no es portable entre dialectos —
un INSERT...SELECT no serviría para ambos a la vez.

Revision ID: d4e8f1a2c6b3
Revises: b7f3a1c9d2e4
Create Date: 2026-11-06 09:05:00.000000
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'd4e8f1a2c6b3'
down_revision: str | None = 'b7f3a1c9d2e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PUENTE = sa.table(
    'factura_agencia_orden',
    sa.column('id', sa.Uuid()),
    sa.column('factura_agencia_id', sa.Uuid()),
    sa.column('orden_id', sa.Uuid()),
    sa.column('porcentaje_comision_snap', sa.Numeric(5, 2)),
    sa.column('comision_calculada', sa.Numeric(14, 2)),
)


def upgrade() -> None:
    conn = op.get_bind()
    # Por seguridad antes del ALTER a NOT NULL del siguiente paso (ver docstring).
    conn.execute(
        sa.text('UPDATE factura_agencia SET comision_agencia = 0 WHERE comision_agencia IS NULL')
    )

    filas = conn.execute(
        sa.text(
            'SELECT factura_agencia_id, orden_id, porcentaje_comision_agencia, comision_agencia '
            'FROM factura_agencia WHERE orden_id IS NOT NULL'
        )
    ).all()
    for fila in filas:
        conn.execute(
            _PUENTE.insert().values(
                id=uuid.uuid4(),
                factura_agencia_id=fila.factura_agencia_id,
                orden_id=fila.orden_id,
                porcentaje_comision_snap=fila.porcentaje_comision_agencia or Decimal('0'),
                comision_calculada=fila.comision_agencia or Decimal('0'),
            )
        )


def downgrade() -> None:
    # Irreversible a propósito: una factura con VARIAS filas en la puente (el objetivo
    # mismo de este cambio) no tiene un único `orden_id`/`%` al que volver — cuál de las
    # varias filas "gana" es ambiguo. `f2a9c5d7e1b8.downgrade()` (que corre ANTES que
    # esta, Alembic baja en reversa) ya restauró las columnas viejas en NULL; se dejan
    # así en vez de adivinar (mismo criterio que `608bd39dc2f2`).
    pass
