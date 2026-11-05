"""f2 f3 backfill facturado_directo

Migración solo de DATOS (sin DDL, mismo patrón que `608bd39dc2f2`): la revisión anterior
agregó `facturado_directo` con `server_default='1'`, así que TODAS las filas existentes
quedaron en `True` (facturación directa) sin importar su receptor real. Aquí se corrige
una sola vez:

1. `factura_cliente.facturado_directo` → `False` donde su(s) orden(es) ligada(s) (vía
   `factura_cliente_orden`) sean `facturacion_directa_cliente = False` CON `agencia_id`
   capturado — validado en el alta (`_receptor_de`) que todas las órdenes de una misma
   factura comparten receptor, así que basta con que UNA lo cumpla.
2. `cobranza_factura.facturado_directo` → se copia de `factura_cliente` (ya corregido
   en el paso 1), mismo criterio que el backfill de `agencia_id` (`608bd39dc2f2`).

Revision ID: 4f286d68a07f
Revises: 2e0c8a75aad5
Create Date: 2026-11-05 14:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '4f286d68a07f'
down_revision: str | None = '2e0c8a75aad5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        'UPDATE factura_cliente SET facturado_directo = 0 '
        'WHERE factura_id IN ('
        '  SELECT fco.factura_id FROM factura_cliente_orden fco '
        '  JOIN orden_cliente oc ON oc.orden_id = fco.orden_id '
        '  WHERE oc.facturacion_directa_cliente = 0 AND oc.agencia_id IS NOT NULL'
        ')'
    )
    op.execute(
        'UPDATE cobranza_factura SET facturado_directo = ('
        'SELECT fc.facturado_directo FROM factura_cliente fc '
        'WHERE fc.factura_id = cobranza_factura.factura_id'
        ')'
    )


def downgrade() -> None:
    # Irreversible a propósito (mismo criterio que `608bd39dc2f2`): no hay forma de
    # distinguir, al revertir, entre un `facturado_directo=True` que YA era así antes de
    # este backfill y uno que este `upgrade` dejó así porque su orden no calificó para
    # el `UPDATE ... = 0`. Bajar de versión deja el dato como está.
    pass
