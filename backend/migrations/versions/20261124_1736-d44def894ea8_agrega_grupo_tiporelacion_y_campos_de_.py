"""agrega grupo TipoRelacion y campos de nota de credito (feature NotasDeCredito)

Revision ID: d44def894ea8
Revises: 5782aa74d8d8
Create Date: 2026-11-24 17:36:08.729971
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# identificadores de revisión, usados por Alembic.
revision: str = 'd44def894ea8'
down_revision: str | None = '5782aa74d8d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mismo valor que `_GRUPOS_SQL` en `app/modules/catalogos/constantes_sistema.py` tras
# agregar `TIPO_RELACION_SAT` — el autogenerate de Alembic NO detecta cambios de
# contenido en un CHECK ya existente, así que este archivo se completó a mano.
_GRUPOS_IN = (
    "'TipoComprobante', 'Serie', 'RegimenFiscal', 'ClaveProdServ', 'ClaveUnidad', "
    "'UsoCFDI', 'FormaPago', 'MetodoPago', 'MonedaSAT', 'MotivoCambio', 'TipoRelacion'"
)
_GRUPOS_IN_SIN_TIPO_RELACION = (
    "'TipoComprobante', 'Serie', 'RegimenFiscal', 'ClaveProdServ', 'ClaveUnidad', "
    "'UsoCFDI', 'FormaPago', 'MetodoPago', 'MonedaSAT', 'MotivoCambio'"
)

#  SQL Server rechaza un operador de comparación (<=, >=) como valor THEN/ELSE de un
#  CASE — un CASE solo puede regresar un valor escalar, no un predicado booleano
#  (SQLite sí lo permite, trata el predicado como 0/1, por eso esto pasaba la validación
#  local y tronaba hasta que se corría contra SQL Server real: "Incorrect syntax near
#  '<'."). Se reescribe como una expresión booleana con OR/AND; `COALESCE(...,'I')`
#  evita que la comparación con `tipo_comprobante` (nullable) propague NULL de vuelta
#  al OR exterior — con NULL de por medio, `NULL OR FALSE` evalúa NULL, y un CHECK
#  trata NULL como "no violado" (aceptaría una fila que debía rechazarse).
_SUBTOTAL_CHECK = (
    "(COALESCE(tipo_comprobante, 'I') = 'E' AND subtotal_factura <= 0) "
    "OR (COALESCE(tipo_comprobante, 'I') <> 'E' AND subtotal_factura >= 0)"
)
_IVA_CHECK = (
    "(COALESCE(tipo_comprobante, 'I') = 'E' AND iva_factura <= 0) "
    "OR (COALESCE(tipo_comprobante, 'I') <> 'E' AND iva_factura >= 0)"
)
_TOTAL_CHECK = (
    "(COALESCE(tipo_comprobante, 'I') = 'E' AND total_factura <= 0) "
    "OR (COALESCE(tipo_comprobante, 'I') <> 'E' AND total_factura >= 0)"
)
_MOTIVO_NOTA_CREDITO_CHECK = (
    "motivo_nota_credito IS NULL OR motivo_nota_credito IN "
    "('devolucion_total', 'devolucion_parcial', 'descuento', 'bonificacion')"
)


def upgrade() -> None:
    # Revisado a mano: el autogenerate también detectó deriva preexistente, sin
    # relación con este cambio (log_envio_correo_orden_estacion, constantes_sistema
    # index→unique, contrato, marca, requisicion) — se descarta. Lo que SÍ es de este
    # cambio (columnas nuevas + los 2 CHECK que el autogenerate no supo detectar) se
    # deja completo abajo.
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("constantes_sistema") as batch_op:
            batch_op.drop_constraint("ck_constantes_sistema_grupo", type_="check")
            batch_op.create_check_constraint(
                "ck_constantes_sistema_grupo", f"grupo IN ({_GRUPOS_IN})"
            )
    else:
        op.drop_constraint(
            "ck_constantes_sistema_grupo", "constantes_sistema", type_="check"
        )
        op.create_check_constraint(
            "ck_constantes_sistema_grupo",
            "constantes_sistema",
            f"grupo IN ({_GRUPOS_IN})",
        )

    if dialect == "sqlite":
        with op.batch_alter_table("factura_cliente") as batch_op:
            batch_op.add_column(
                sa.Column("motivo_nota_credito", sa.Unicode(length=30), nullable=True)
            )
            batch_op.add_column(
                sa.Column("tipo_relacion_sat", sa.Unicode(length=2), nullable=True)
            )
            batch_op.drop_constraint("ck_factura_cliente_subtotal", type_="check")
            batch_op.drop_constraint("ck_factura_cliente_iva", type_="check")
            batch_op.drop_constraint("ck_factura_cliente_total", type_="check")
            batch_op.create_check_constraint("ck_factura_cliente_subtotal", _SUBTOTAL_CHECK)
            batch_op.create_check_constraint("ck_factura_cliente_iva", _IVA_CHECK)
            batch_op.create_check_constraint("ck_factura_cliente_total", _TOTAL_CHECK)
            batch_op.create_check_constraint(
                "ck_factura_cliente_motivo_nota_credito", _MOTIVO_NOTA_CREDITO_CHECK
            )
    else:
        op.add_column(
            "factura_cliente",
            sa.Column("motivo_nota_credito", sa.Unicode(length=30), nullable=True),
        )
        op.add_column(
            "factura_cliente",
            sa.Column("tipo_relacion_sat", sa.Unicode(length=2), nullable=True),
        )
        op.drop_constraint("ck_factura_cliente_subtotal", "factura_cliente", type_="check")
        op.drop_constraint("ck_factura_cliente_iva", "factura_cliente", type_="check")
        op.drop_constraint("ck_factura_cliente_total", "factura_cliente", type_="check")
        op.create_check_constraint(
            "ck_factura_cliente_subtotal", "factura_cliente", _SUBTOTAL_CHECK
        )
        op.create_check_constraint("ck_factura_cliente_iva", "factura_cliente", _IVA_CHECK)
        op.create_check_constraint(
            "ck_factura_cliente_total", "factura_cliente", _TOTAL_CHECK
        )
        op.create_check_constraint(
            "ck_factura_cliente_motivo_nota_credito",
            "factura_cliente",
            _MOTIVO_NOTA_CREDITO_CHECK,
        )

    op.add_column("pago_cliente", sa.Column("factura_egreso_id", sa.Uuid(), nullable=True))
    if dialect == "sqlite":
        with op.batch_alter_table("pago_cliente") as batch_op:
            batch_op.create_unique_constraint(
                "uq_pago_cliente_factura_egreso", ["factura_egreso_id"]
            )
            batch_op.create_foreign_key(
                "fk_pago_cliente_factura_egreso",
                "factura_cliente",
                ["factura_egreso_id"],
                ["factura_id"],
            )
    else:
        op.create_unique_constraint(
            "uq_pago_cliente_factura_egreso", "pago_cliente", ["factura_egreso_id"]
        )
        op.create_foreign_key(
            "fk_pago_cliente_factura_egreso",
            "pago_cliente",
            "factura_cliente",
            ["factura_egreso_id"],
            ["factura_id"],
            ondelete="NO ACTION",
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("pago_cliente") as batch_op:
            batch_op.drop_constraint("fk_pago_cliente_factura_egreso", type_="foreignkey")
            batch_op.drop_constraint("uq_pago_cliente_factura_egreso", type_="unique")
            batch_op.drop_column("factura_egreso_id")
    else:
        op.drop_constraint(
            "fk_pago_cliente_factura_egreso", "pago_cliente", type_="foreignkey"
        )
        op.drop_constraint(
            "uq_pago_cliente_factura_egreso", "pago_cliente", type_="unique"
        )
        op.drop_column("pago_cliente", "factura_egreso_id")

    if dialect == "sqlite":
        with op.batch_alter_table("factura_cliente") as batch_op:
            batch_op.drop_constraint(
                "ck_factura_cliente_motivo_nota_credito", type_="check"
            )
            batch_op.drop_constraint("ck_factura_cliente_total", type_="check")
            batch_op.drop_constraint("ck_factura_cliente_iva", type_="check")
            batch_op.drop_constraint("ck_factura_cliente_subtotal", type_="check")
            batch_op.create_check_constraint(
                "ck_factura_cliente_subtotal", "subtotal_factura >= 0"
            )
            batch_op.create_check_constraint("ck_factura_cliente_iva", "iva_factura >= 0")
            batch_op.create_check_constraint(
                "ck_factura_cliente_total", "total_factura >= 0"
            )
            batch_op.drop_column("tipo_relacion_sat")
            batch_op.drop_column("motivo_nota_credito")
    else:
        op.drop_constraint(
            "ck_factura_cliente_motivo_nota_credito", "factura_cliente", type_="check"
        )
        op.drop_constraint("ck_factura_cliente_total", "factura_cliente", type_="check")
        op.drop_constraint("ck_factura_cliente_iva", "factura_cliente", type_="check")
        op.drop_constraint("ck_factura_cliente_subtotal", "factura_cliente", type_="check")
        op.create_check_constraint(
            "ck_factura_cliente_subtotal", "factura_cliente", "subtotal_factura >= 0"
        )
        op.create_check_constraint(
            "ck_factura_cliente_iva", "factura_cliente", "iva_factura >= 0"
        )
        op.create_check_constraint(
            "ck_factura_cliente_total", "factura_cliente", "total_factura >= 0"
        )
        op.drop_column("factura_cliente", "tipo_relacion_sat")
        op.drop_column("factura_cliente", "motivo_nota_credito")

    if dialect == "sqlite":
        with op.batch_alter_table("constantes_sistema") as batch_op:
            batch_op.drop_constraint("ck_constantes_sistema_grupo", type_="check")
            batch_op.create_check_constraint(
                "ck_constantes_sistema_grupo",
                f"grupo IN ({_GRUPOS_IN_SIN_TIPO_RELACION})",
            )
    else:
        op.drop_constraint(
            "ck_constantes_sistema_grupo", "constantes_sistema", type_="check"
        )
        op.create_check_constraint(
            "ck_constantes_sistema_grupo",
            "constantes_sistema",
            f"grupo IN ({_GRUPOS_IN_SIN_TIPO_RELACION})",
        )
