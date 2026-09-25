"""f1 orden_estacion_dia cancelada

ADR-104 (petición del usuario) — Fase 4b del rediseño "Cancelar transmisión": columna
nueva `cancelada` (BIT, default 0) en `orden_estacion_dia`. Un día cancelado queda
excluido de las sumas de `spots_asignados` (balance de spots de la OC e importe de la
OE) pero conserva su fila y su `Verificacion`/`Incidencia` generadas al cancelar.

`add_column` con `server_default='0'` funciona igual en SQLite y SQL Server (mismo
criterio que ADR-067/`a4c7fe6279b2`) — no necesita rama por dialecto. El `downgrade` sí
la necesita: en SQL Server, `server_default` crea un DEFAULT CONSTRAINT autogenerado que
bloquea el `DROP COLUMN` si no se suelta antes.

Revision ID: e262550019b7
Revises: a361d2e883be
Create Date: 2026-09-23 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'e262550019b7'
down_revision: str | None = 'a361d2e883be'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'orden_estacion_dia',
        sa.Column('cancelada', sa.Boolean(), nullable=False, server_default='0'),
    )


def _drop_default_constraint_mssql(tabla: str, columna: str) -> None:
    """Ver docstring del módulo: `server_default` en SQL Server crea un DEFAULT
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
        with op.batch_alter_table('orden_estacion_dia') as batch:
            batch.drop_column('cancelada')
    else:
        _drop_default_constraint_mssql('orden_estacion_dia', 'cancelada')
        op.drop_column('orden_estacion_dia', 'cancelada')
