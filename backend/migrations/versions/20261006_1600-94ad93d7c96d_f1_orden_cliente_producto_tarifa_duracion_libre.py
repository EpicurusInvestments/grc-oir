"""f1 orden cliente producto tarifa duracion libre

ADR-167 (petición del usuario): "Orden de Servicio" (OrdenCliente) conecta su sección
"Campaña y montos" al catálogo `DuracionSpotCatalogo` ("Producto Duración", F0-06), igual
que Tarifa (ADR-166) — Producto primero, Duración se llena según el Producto elegido.
A diferencia de Tarifa, aquí SÍ se puede dejar sin capturar una duración real (p.ej.
Mención, cuyo catálogo solo tiene "sin resultado"): `duracion_spot` deja el CHECK
`20s|30s|60s` y se vuelve NULLABLE + texto libre; se agrega `producto_tarifa` (texto
libre, también NULLABLE, nuevo — fuera de la spec BD v2, mismo criterio que
`TarifaPlaza.producto`, ADR-097).

Sin migración de datos: los valores ya capturados con el enum anterior siguen siendo
cadenas válidas.

Revision ID: 94ad93d7c96d
Revises: f4c9c5db55eb
Create Date: 2026-10-06 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '94ad93d7c96d'
down_revision: str | None = 'f4c9c5db55eb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_cliente') as batch:
            batch.drop_constraint('ck_orden_cliente_duracion_spot', type_='check')
            batch.alter_column(
                'duracion_spot',
                existing_type=sa.Unicode(length=10),
                type_=sa.Unicode(length=60),
                nullable=True,
            )
            batch.add_column(sa.Column('producto_tarifa', sa.Unicode(length=60), nullable=True))
    else:
        op.drop_constraint('ck_orden_cliente_duracion_spot', 'orden_cliente', type_='check')
        op.alter_column(
            'orden_cliente', 'duracion_spot',
            existing_type=sa.Unicode(length=10), type_=sa.Unicode(length=60),
            nullable=True,
        )
        op.add_column(
            'orden_cliente', sa.Column('producto_tarifa', sa.Unicode(length=60), nullable=True)
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_cliente') as batch:
            batch.drop_column('producto_tarifa')
            batch.alter_column(
                'duracion_spot',
                existing_type=sa.Unicode(length=60),
                type_=sa.Unicode(length=10),
                nullable=False,
            )
            batch.create_check_constraint(
                'ck_orden_cliente_duracion_spot', "duracion_spot IN ('20s', '30s', '60s')"
            )
    else:
        op.drop_column('orden_cliente', 'producto_tarifa')
        op.alter_column(
            'orden_cliente', 'duracion_spot',
            existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=10),
            nullable=False,
        )
        op.create_check_constraint(
            'ck_orden_cliente_duracion_spot', 'orden_cliente',
            "duracion_spot IN ('20s', '30s', '60s')",
        )
