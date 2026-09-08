"""f2 uso cfdi default anunciante y factura cliente

Agrega `uso_cfdi_default` (clave SAT c_UsoCFDI, sugerida desde `ConstantesSistema` grupo
UsoCFDI, sin FK formal — mismo patrón que `regimen_fiscal`/`metodo_pago_clave`) a
`Anunciante`, y `uso_cfdi` a `FacturaCliente`.

Segunda mitad de ADR-065: `AGREGADOS.UsoCFDI` dejó de resolverse vía
`_constante_unica("UsoCFDI")` — "exactamente una activa o falta" — para capturarse de
verdad por factura. `Anunciante.uso_cfdi_default` es solo la SUGERENCIA que precarga el
formulario cuando el receptor es el anunciante directo (sin agencia); lo que se timbra
es siempre `FacturaCliente.uso_cfdi`, editable en cada factura sin importar cuál sea el
receptor.

2 columnas nuevas y nullable: no se pierde nada, se llenan hacia adelante.

Nota: el autogenerate volvió a detectar las 2 operaciones de índice ajenas a este cambio
(`ix_contrato_estado_contrato` removido, `ix_marca_nombre_marca` agregado) — es la
deriva de índices de F0 ya documentada en `docs/modulos/f2-facturacion/f2-facturacion.md`
("Pendientes / dudas"), no relacionada con `uso_cfdi`. Se excluyeron de esta migración a
propósito (mismo criterio que la migración anterior, ADR-065 de `regimen_fiscal`).

Revision ID: ebdf80f59dd1
Revises: 7d5f9c4589c0
Create Date: 2026-09-08 11:44:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'ebdf80f59dd1'
down_revision: str | None = '7d5f9c4589c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('anunciante', sa.Column('uso_cfdi_default', sa.Unicode(length=5), nullable=True))
    op.add_column('factura_cliente', sa.Column('uso_cfdi', sa.Unicode(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column('factura_cliente', 'uso_cfdi')
    op.drop_column('anunciante', 'uso_cfdi_default')
