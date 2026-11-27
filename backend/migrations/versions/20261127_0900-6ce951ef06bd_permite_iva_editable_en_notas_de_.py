"""permite IVA editable en Notas de Credito (petición del usuario 2026-11-27)

Revision ID: 6ce951ef06bd
Revises: a45105db6ff1
Create Date: 2026-11-27 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '6ce951ef06bd'
down_revision: str | None = 'a45105db6ff1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Revisado a mano: el autogenerate de Alembic NO detecta cambios de contenido en un
# CHECK ya existente (mismo motivo que `d44def894ea8`).
#
# `CASE WHEN` y NO `tipo_comprobante = 'E' OR ...`: con `tipo_comprobante` NULL
# (facturas viejas) una comparación `= 'E'` da NULL, y `NULL OR falso` es NULL — que un
# CHECK trata como "pasa" (bug real, detectado por
# `test_check_del_iva_rechaza_una_tasa_distinta_del_16` al correr la suite completa).
_IVA_CALCULADO_CON_EXCEPCION_NC = (
    "CASE WHEN tipo_comprobante = 'E' THEN 1 = 1 "
    "ELSE ROUND(iva_factura, 2) = ROUND(subtotal_factura * 0.16, 2) END"
)
_IVA_CALCULADO_SIN_EXCEPCION = "ROUND(iva_factura, 2) = ROUND(subtotal_factura * 0.16, 2)"


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("factura_cliente") as batch_op:
            batch_op.drop_constraint("ck_factura_cliente_iva_calculado", type_="check")
            batch_op.create_check_constraint(
                "ck_factura_cliente_iva_calculado", _IVA_CALCULADO_CON_EXCEPCION_NC
            )
    else:
        op.drop_constraint(
            "ck_factura_cliente_iva_calculado", "factura_cliente", type_="check"
        )
        op.create_check_constraint(
            "ck_factura_cliente_iva_calculado",
            "factura_cliente",
            _IVA_CALCULADO_CON_EXCEPCION_NC,
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("factura_cliente") as batch_op:
            batch_op.drop_constraint("ck_factura_cliente_iva_calculado", type_="check")
            batch_op.create_check_constraint(
                "ck_factura_cliente_iva_calculado", _IVA_CALCULADO_SIN_EXCEPCION
            )
    else:
        op.drop_constraint(
            "ck_factura_cliente_iva_calculado", "factura_cliente", type_="check"
        )
        op.create_check_constraint(
            "ck_factura_cliente_iva_calculado",
            "factura_cliente",
            _IVA_CALCULADO_SIN_EXCEPCION,
        )
