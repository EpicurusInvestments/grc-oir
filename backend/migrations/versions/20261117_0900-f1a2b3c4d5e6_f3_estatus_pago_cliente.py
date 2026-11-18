"""f3 estatus_pago pago_cliente

ADR-271 (petición del usuario, "Cancelación de Pago", con desarrolladores consultados):
nueva columna `estatus_pago` ('pagado'/'cancelado') en `pago_cliente` — reemplaza el
borrado físico de un pago YA ASIGNADO a una factura (ADR-035) por una baja lógica: al
cancelar, la fila se queda (visible en el historial con su estatus) en vez de
desaparecer, y `importe_cobrado()` la excluye de la suma. Un pago SIN asignar sigue
borrándose físico (no toca ninguna factura, ver `PagoClienteService.eliminar`).

Sin backfill: todas las filas existentes son pagos activos — `default='pagado'` para
todas es correcto desde el día 1.

Revision ID: f1a2b3c4d5e6
Revises: e6f7a8b9c0d1
Create Date: 2026-11-17 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'e6f7a8b9c0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = 'pago_cliente'
_CHECK = 'ck_pago_cliente_estatus_pago'


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.add_column(
                sa.Column(
                    'estatus_pago', sa.Unicode(20), nullable=False, server_default='pagado'
                )
            )
            batch.create_check_constraint(_CHECK, "estatus_pago IN ('pagado', 'cancelado')")
    else:
        op.add_column(
            _TABLA,
            sa.Column('estatus_pago', sa.Unicode(20), nullable=False, server_default='pagado'),
        )
        op.create_check_constraint(_CHECK, _TABLA, "estatus_pago IN ('pagado', 'cancelado')")


def _drop_default_constraint_mssql(tabla: str, columna: str) -> None:
    """Ver docstring de `7b931c7fdb4e`: `server_default` en SQL Server crea un DEFAULT
    CONSTRAINT con nombre autogenerado que hay que soltar antes del `DROP COLUMN`."""
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
        with op.batch_alter_table(_TABLA) as batch:
            batch.drop_constraint(_CHECK, type_='check')
            batch.drop_column('estatus_pago')
    else:
        op.drop_constraint(_CHECK, _TABLA, type_='check')
        _drop_default_constraint_mssql(_TABLA, 'estatus_pago')
        op.drop_column(_TABLA, 'estatus_pago')
