"""f3 backfill agencia_id cobranza_factura

Migración solo de DATOS (sin DDL): ADR-225 agregó `cobranza_factura.agencia_id`,
derivado de `factura_cliente.agencia_id` SOLO en el momento de crear la `CobranzaFactura`
(`crear_para_factura`, invocado al timbrar). Las `CobranzaFactura` que ya existían de
ANTES de ese ADR se quedaron con `agencia_id = NULL` para siempre — nada las recalcula
retroactivamente — así que la columna "Agencia" de la lista (petición del usuario, este
mismo día) les sale vacía aunque su `FacturaCliente` sí tenga agencia. Se corrige una
sola vez, copiando el dato real desde `factura_cliente`.

Mismo patrón que la revisión `5da59f306b51` (copiar datos existentes con `op.execute`
antes de un cambio de esquema) — aquí no hay cambio de esquema, solo el `UPDATE`.

Revision ID: 608bd39dc2f2
Revises: c3d8f2a914be
Create Date: 2026-11-04 03:00:23.196923
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '608bd39dc2f2'
down_revision: str | None = 'c3d8f2a914be'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        'UPDATE cobranza_factura SET agencia_id = ('
        'SELECT fc.agencia_id FROM factura_cliente fc '
        'WHERE fc.factura_id = cobranza_factura.factura_id'
        ') WHERE agencia_id IS NULL'
    )


def downgrade() -> None:
    # Irreversible a propósito: no hay forma de distinguir, al revertir, entre un
    # `agencia_id` que YA era NULL antes de este backfill (facturación directa de
    # verdad) y uno que este `upgrade` dejó en NULL porque su `FacturaCliente` tampoco
    # tenía agencia — ambos casos son indistinguibles después del hecho. Bajar de
    # versión deja el dato como está (no se pierde nada: solo se dejaron de rellenar
    # NULLs, nunca se sobrescribió un valor existente).
    pass
