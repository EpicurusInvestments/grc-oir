"""f1 spots bonificables orden cliente

Agrega `cantidad_spots_bonificables` (spots que se transmiten normalmente pero no se
cobran al cliente) y `subtotal_spots_bonificables` (calculado, nunca capturado) a
`OrdenCliente` (ADR-067). Ambas columnas quedan NOT NULL con default `0` — las órdenes
existentes no tenían bonificación, así que `0` es el valor neutro: su `subtotal`/`iva`/
`total` ya calculados no cambian.

`total_spots` NO cambia de significado: sigue siendo el total real que se asigna a
`OrdenEstacion` y se transmite. Los spots bonificables son un descuento COMERCIAL sobre
lo que se le cobra al cliente, no sobre lo que se transmite — este cambio queda
contenido en `OrdenCliente`, sin tocar `OrdenEstacion`.

Nota: el autogenerate también detectó las 2 operaciones de índice ajenas a este cambio
(`ix_contrato_estado_contrato` removido, `ix_marca_nombre_marca` agregado) — es la
deriva de índices de F0 ya documentada, no relacionada con `spots_bonificables`. Se
excluyeron de esta migración a propósito (mismo criterio que las migraciones de
ADR-065/065 bis).

Los 3 CHECK nuevos necesitan la rama por dialecto de ADR-063: SQLite no soporta ALTER de
constraints fuera del batch mode (recrea la tabla), mientras que en SQL Server es un
ALTER normal. Los `add_column` en sí SÍ funcionan igual en ambos dialectos (con
`server_default='0'` para no dejar NULL las filas existentes), así que no necesitan la
rama — solo los `CheckConstraint`.

Revision ID: a4c7fe6279b2
Revises: a9b3cdeef9e7
Create Date: 2026-09-09 15:22:14.139237
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a4c7fe6279b2'
down_revision: str | None = 'a9b3cdeef9e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECKS: tuple[tuple[str, str], ...] = (
    ('ck_orden_cliente_spots_bonificables', 'cantidad_spots_bonificables >= 0'),
    (
        'ck_orden_cliente_spots_bonificables_no_excede',
        'cantidad_spots_bonificables <= total_spots',
    ),
    ('ck_orden_cliente_subtotal_bonificables', 'subtotal_spots_bonificables >= 0'),
)


def upgrade() -> None:
    op.add_column(
        'orden_cliente',
        sa.Column(
            'cantidad_spots_bonificables', sa.Integer(), nullable=False, server_default='0'
        ),
    )
    op.add_column(
        'orden_cliente',
        sa.Column(
            'subtotal_spots_bonificables',
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default='0',
        ),
    )
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_cliente') as batch:
            for nombre, condicion in _CHECKS:
                batch.create_check_constraint(nombre, condicion)
    else:
        for nombre, condicion in _CHECKS:
            op.create_check_constraint(nombre, 'orden_cliente', condicion)


def _drop_default_constraint_mssql(tabla: str, columna: str) -> None:
    """`server_default` en SQL Server crea un DEFAULT CONSTRAINT con nombre
    AUTOGENERADO (`DF__orden_cli__...`) que bloquea el `DROP COLUMN` si no se suelta
    antes — a diferencia de SQLite, donde el batch mode recrea la tabla completa y este
    problema no existe."""
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
        with op.batch_alter_table('orden_cliente') as batch:
            for nombre, _condicion in reversed(_CHECKS):
                batch.drop_constraint(nombre, type_='check')
        op.drop_column('orden_cliente', 'subtotal_spots_bonificables')
        op.drop_column('orden_cliente', 'cantidad_spots_bonificables')
    else:
        for nombre, _condicion in reversed(_CHECKS):
            op.drop_constraint(nombre, 'orden_cliente', type_='check')
        _drop_default_constraint_mssql('orden_cliente', 'subtotal_spots_bonificables')
        op.drop_column('orden_cliente', 'subtotal_spots_bonificables')
        _drop_default_constraint_mssql('orden_cliente', 'cantidad_spots_bonificables')
        op.drop_column('orden_cliente', 'cantidad_spots_bonificables')
