"""requisicion tipo devolucion (Nota de Credito a factura ya cobrada, ADR-297)

Revision ID: 662d28ca5580
Revises: 6ce951ef06bd
Create Date: 2026-11-27 17:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '662d28ca5580'
down_revision: str | None = '6ce951ef06bd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Revisado a mano: el autogenerate de Alembic NO detecta cambios de contenido en un
# CHECK ya existente (mismo motivo que `d44def894ea8`/`6ce951ef06bd`).
_TIPOS_CON_DEVOLUCION = (
    "'pago_afiliado', 'pago_agencia', 'comision_vendedor', 'comision_agencia', 'devolucion'"
)
_TIPOS_SIN_DEVOLUCION = "'pago_afiliado', 'pago_agencia', 'comision_vendedor', 'comision_agencia'"


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("requisicion") as batch_op:
            batch_op.add_column(sa.Column("factura_cliente_id", sa.Uuid(), nullable=True))
            batch_op.add_column(
                sa.Column("razon_social_cliente", sa.Unicode(length=200), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_requisicion_factura_cliente",
                "factura_cliente",
                ["factura_cliente_id"],
                ["factura_id"],
            )
            batch_op.drop_constraint("ck_requisicion_tipo", type_="check")
            batch_op.create_check_constraint(
                "ck_requisicion_tipo", f"tipo_requisicion IN ({_TIPOS_CON_DEVOLUCION})"
            )
    else:
        op.add_column(
            "requisicion", sa.Column("factura_cliente_id", sa.Uuid(), nullable=True)
        )
        op.add_column(
            "requisicion",
            sa.Column("razon_social_cliente", sa.Unicode(length=200), nullable=True),
        )
        op.create_foreign_key(
            "fk_requisicion_factura_cliente",
            "requisicion",
            "factura_cliente",
            ["factura_cliente_id"],
            ["factura_id"],
            ondelete="NO ACTION",
        )
        op.drop_constraint("ck_requisicion_tipo", "requisicion", type_="check")
        op.create_check_constraint(
            "ck_requisicion_tipo",
            "requisicion",
            f"tipo_requisicion IN ({_TIPOS_CON_DEVOLUCION})",
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("requisicion") as batch_op:
            batch_op.drop_constraint("ck_requisicion_tipo", type_="check")
            batch_op.create_check_constraint(
                "ck_requisicion_tipo", f"tipo_requisicion IN ({_TIPOS_SIN_DEVOLUCION})"
            )
            batch_op.drop_constraint("fk_requisicion_factura_cliente", type_="foreignkey")
            batch_op.drop_column("razon_social_cliente")
            batch_op.drop_column("factura_cliente_id")
    else:
        op.drop_constraint("ck_requisicion_tipo", "requisicion", type_="check")
        op.create_check_constraint(
            "ck_requisicion_tipo",
            "requisicion",
            f"tipo_requisicion IN ({_TIPOS_SIN_DEVOLUCION})",
        )
        op.drop_constraint(
            "fk_requisicion_factura_cliente", "requisicion", type_="foreignkey"
        )
        op.drop_column("requisicion", "razon_social_cliente")
        op.drop_column("requisicion", "factura_cliente_id")
