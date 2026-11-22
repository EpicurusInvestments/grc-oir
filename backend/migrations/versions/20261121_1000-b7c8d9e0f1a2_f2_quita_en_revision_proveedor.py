"""f2 quita en_revision de facturas proveedor

ADR-282 (petición del usuario, con captura): se elimina el estatus intermedio
`en_revision` de `FacturaAfiliado`/`FacturaAgencia`/`FacturaVendedor` — el flujo pasa de
`recibida -> en_revision -> autorizada -> pagada` a `recibida -> autorizada -> pagada`
directo. Afecta las 3 entidades por igual: comparten el mismo enum
`EstatusFacturaProveedor` y la misma máquina de estados (`TRANSICIONES_PROVEEDOR`).

Backfill defensivo: cualquier fila que hoy esté en `en_revision` se regresa a
`recibida` (equivalente a "Devolver a capturista") antes de endurecer el CHECK —
en la BD de desarrollo no había ninguna al momento de escribir esta migración, pero
una BD distinta sí podría tenerlas.

Revision ID: b7c8d9e0f1a2
Revises: a4b5c6d7e8f9
Create Date: 2026-11-21 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: str | None = 'a4b5c6d7e8f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTIDADES = [
    ('factura_afiliado', 'estatus_factura_afiliado', 'ck_factura_afiliado_estatus'),
    ('factura_agencia', 'estatus_factura_agencia', 'ck_factura_agencia_estatus'),
    ('factura_vendedor', 'estatus_factura_vendedor', 'ck_factura_vendedor_estatus'),
]

_CONDICION_NUEVA = "IN ('recibida', 'autorizada', 'pagada')"
_CONDICION_VIEJA = "IN ('recibida', 'en_revision', 'autorizada', 'pagada')"


def upgrade() -> None:
    es_sqlite = op.get_bind().dialect.name == 'sqlite'
    for tabla, columna, check in _ENTIDADES:
        op.execute(f"UPDATE {tabla} SET {columna} = 'recibida' WHERE {columna} = 'en_revision'")
        if es_sqlite:
            with op.batch_alter_table(tabla) as batch:
                batch.drop_constraint(check, type_='check')
                batch.create_check_constraint(check, f"{columna} {_CONDICION_NUEVA}")
        else:
            op.drop_constraint(check, tabla, type_='check')
            op.create_check_constraint(check, tabla, f"{columna} {_CONDICION_NUEVA}")


def downgrade() -> None:
    es_sqlite = op.get_bind().dialect.name == 'sqlite'
    for tabla, columna, check in _ENTIDADES:
        if es_sqlite:
            with op.batch_alter_table(tabla) as batch:
                batch.drop_constraint(check, type_='check')
                batch.create_check_constraint(check, f"{columna} {_CONDICION_VIEJA}")
        else:
            op.drop_constraint(check, tabla, type_='check')
            op.create_check_constraint(check, tabla, f"{columna} {_CONDICION_VIEJA}")
