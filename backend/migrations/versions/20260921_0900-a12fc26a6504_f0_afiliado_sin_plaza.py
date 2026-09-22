"""f0 afiliado sin plaza

ADR-096 (petición del usuario): el Afiliado deja de tener `plaza_id` propio — la plaza es
una propiedad de la Estación (ADR-094 ya la capturaba de forma libre e independiente),
no del Afiliado, que puede operar estaciones en varias plazas distintas. Se elimina la
columna, su FK y su índice de `afiliado`. Nada cambia en `estacion` (ya tenía su propio
`plaza_id` desde ADR-094).

Consecuencia en negocio: Plaza ya NO bloquea su baja por "afiliados activos" (ese conteo
dependía de `Afiliado.plaza_id`, que deja de existir) — solo por estaciones activas.

La FK de `afiliado.plaza_id` se creó SIN nombre explícito
(`sa.ForeignKeyConstraint(['plaza_id'], ['plaza.plaza_id'])` en `7300e6f940a3`), así que
SQL Server le asignó un nombre de sistema no determinista (`FK__afiliado__...`) — se
descubre y suelta dinámicamente vía `sys.foreign_keys`, mismo patrón que
`_drop_default_constraint_mssql` en `a4c7fe6279b2` (ADR-067) mas para FK en vez de
DEFAULT. El índice sí es determinista (`ix_afiliado_plaza_id`, vía `op.f()`), se suelta
por nombre directo.

Revision ID: a12fc26a6504
Revises: 3d82c1b995f2
Create Date: 2026-09-21 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a12fc26a6504'
down_revision: str | None = '3d82c1b995f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_fk_mssql(tabla: str, columna: str) -> None:
    """Descubre y suelta la FK de sistema (nombre no determinista) que referencia
    `columna` en `tabla`, antes de poder soltar la columna."""
    op.execute(
        f"""
        DECLARE @constraint_name NVARCHAR(200)
        SELECT @constraint_name = fk.name
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.columns c
            ON c.object_id = fkc.parent_object_id AND c.column_id = fkc.parent_column_id
        WHERE fk.parent_object_id = OBJECT_ID('{tabla}') AND c.name = '{columna}'
        IF @constraint_name IS NOT NULL
            EXEC('ALTER TABLE {tabla} DROP CONSTRAINT ' + @constraint_name)
        """
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('afiliado') as batch:
            batch.drop_index('ix_afiliado_plaza_id')
            batch.drop_column('plaza_id')
    else:
        _drop_fk_mssql('afiliado', 'plaza_id')
        op.drop_index('ix_afiliado_plaza_id', table_name='afiliado')
        op.drop_column('afiliado', 'plaza_id')


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('afiliado') as batch:
            batch.add_column(sa.Column('plaza_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_afiliado_plaza_id_plaza', 'plaza', ['plaza_id'], ['plaza_id']
            )
            batch.create_index('ix_afiliado_plaza_id', ['plaza_id'])
    else:
        op.add_column('afiliado', sa.Column('plaza_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_afiliado_plaza_id_plaza', 'afiliado', 'plaza', ['plaza_id'], ['plaza_id']
        )
        op.create_index(op.f('ix_afiliado_plaza_id'), 'afiliado', ['plaza_id'], unique=False)
