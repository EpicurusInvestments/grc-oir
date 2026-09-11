"""f1 spots bonificables orden estacion

Agrega `cantidad_spots_bonificables` a `OrdenEstacion` (ADR-068): spots que se asignan y
se transmiten igual que cualquier otro (el balance contra `OrdenCliente.total_spots` no
cambia) pero no se cobran a la estación — reducen `importe_estacion` en el servicio, no
en una columna calculada propia (a diferencia de `OrdenCliente.subtotal_spots_bonificables`,
aquí no hace falta: `importe_estacion` YA es el único monto derivado que existe). NOT
NULL con default `0` — las OE existentes no tenían bonificación, así que `0` es el valor
neutro: su `importe_estacion` ya calculado no cambia.

No hay CHECK "`cantidad_spots_bonificables` <= spots asignados": ese total no es una
columna propia de `orden_estacion` (se agrega sobre `orden_estacion_dia`, tabla hija), así
que esa validación vive en el servicio (`OrdenEstacionService.create`/`update`), no en una
constraint expresable en una sola tabla.

`server_default='0'` en SQL Server crea un DEFAULT CONSTRAINT con nombre autogenerado que
bloquea un `DROP COLUMN` posterior si no se suelta antes — mismo hallazgo que en la
migración de `cantidad_spots_bonificables` de `orden_cliente` (ver ADR-067); el
`downgrade()` de aquí reusa el mismo patrón de solución.

Nota: el autogenerate también detectó las 2 operaciones de índice ajenas a este cambio
(`ix_contrato_estado_contrato` removido, `ix_marca_nombre_marca` agregado) — es la deriva
de índices de F0 ya documentada, no relacionada con `spots_bonificables`. Se excluyeron de
esta migración a propósito (mismo criterio que ADR-065/065 bis/067).

Revision ID: 00b9c6d6a5a1
Revises: a4c7fe6279b2
Create Date: 2026-09-10 11:23:36.011273
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '00b9c6d6a5a1'
down_revision: str | None = 'a4c7fe6279b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_NOMBRE = 'ck_orden_estacion_spots_bonificables'
_CHECK_CONDICION = 'cantidad_spots_bonificables >= 0'


def upgrade() -> None:
    op.add_column(
        'orden_estacion',
        sa.Column(
            'cantidad_spots_bonificables', sa.Integer(), nullable=False, server_default='0'
        ),
    )
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.create_check_constraint(_CHECK_NOMBRE, _CHECK_CONDICION)
    else:
        op.create_check_constraint(_CHECK_NOMBRE, 'orden_estacion', _CHECK_CONDICION)


def _drop_default_constraint_mssql(tabla: str, columna: str) -> None:
    """Ver docstring del módulo: `server_default` en SQL Server crea un DEFAULT
    CONSTRAINT con nombre AUTOGENERADO que bloquea el `DROP COLUMN` si no se suelta
    antes — a diferencia de SQLite, donde el batch mode recrea la tabla completa."""
    op.execute(
        f"""
        DECLARE @constraint_name NVARCHAR(200)
        SELECT @constraint_name = dc.name
        FROM sys.default_constraints dc
        JOIN sys.columns c
            ON c.default_object_id = dc.object_id AND c.object_id = dc.parent_object_id
        WHERE dc.parent_object_id = OBJECT_ID('{tabla}') AND c.name = '{columna}'
        IF @constraint_name IS NOT NULL
            EXEC('ALTER TABLE {tabla} DROP CONSTRAINT ' + @constraint_name)
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.drop_constraint(_CHECK_NOMBRE, type_='check')
        op.drop_column('orden_estacion', 'cantidad_spots_bonificables')
    else:
        op.drop_constraint(_CHECK_NOMBRE, 'orden_estacion', type_='check')
        _drop_default_constraint_mssql('orden_estacion', 'cantidad_spots_bonificables')
        op.drop_column('orden_estacion', 'cantidad_spots_bonificables')
