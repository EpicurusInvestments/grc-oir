"""f1 orden estacion dia horario unico

ADR-108/ADR-112: "Horario de transmisión" pasó de ser un rango (hora_inicio < hora_fin)
a un solo valor capturado una vez y guardado en ambas columnas — el frontend manda
siempre `hora_inicio == hora_fin`. `ck_orden_estacion_dia_horas` seguía exigiendo
`hora_fin > hora_inicio` (estrictamente), lo que rechazaba con 422/500 TODA alta o
edición de OrdenEstacion desde que se implementó ADR-108 en el frontend — se relaja a
`hora_fin >= hora_inicio`.

Revision ID: c3162961f659
Revises: fb5e4af2dd28
Create Date: 2026-09-23 14:03:56.202564
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'c3162961f659'
down_revision: str | None = 'fb5e4af2dd28'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion_dia') as batch:
            batch.drop_constraint('ck_orden_estacion_dia_horas', type_='check')
            batch.create_check_constraint('ck_orden_estacion_dia_horas', 'hora_fin >= hora_inicio')
    else:
        op.drop_constraint('ck_orden_estacion_dia_horas', 'orden_estacion_dia', type_='check')
        op.create_check_constraint(
            'ck_orden_estacion_dia_horas', 'orden_estacion_dia', 'hora_fin >= hora_inicio'
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion_dia') as batch:
            batch.drop_constraint('ck_orden_estacion_dia_horas', type_='check')
            batch.create_check_constraint('ck_orden_estacion_dia_horas', 'hora_fin > hora_inicio')
    else:
        op.drop_constraint('ck_orden_estacion_dia_horas', 'orden_estacion_dia', type_='check')
        op.create_check_constraint(
            'ck_orden_estacion_dia_horas', 'orden_estacion_dia', 'hora_fin > hora_inicio'
        )
