"""f0 regimen fiscal empresa facturadora anunciante agencia

Agrega `regimen_fiscal` (clave SAT del catálogo c_RegimenFiscal, sugerida desde
`ConstantesSistema` grupo RegimenFiscal, sin FK formal — mismo patrón que
`metodo_pago_clave` en F2) a `EmpresaFacturadora`, `Anunciante` y `Agencia`.

Reemplaza la resolución vía `_constante_unica("RegimenFiscal")` en
`FacturaClienteService._datos_timbrado()`, que dejó de servir en cuanto el catálogo tuvo
más de una constante activa en ese grupo (regla: "exactamente una activa o se reporta
como faltante" — con varias, ambiguo a propósito). Ahora cada entidad captura el suyo:
`EmpresaFacturadora.regimen_fiscal` es el del EMISOR; `Anunciante.regimen_fiscal` o
`Agencia.regimen_fiscal` es el del RECEPTOR, según quién sea el receptor real de la
factura (trato directo vs. vía agencia).

3 columnas nuevas y nullable: no se pierde nada, se llenan hacia adelante.

Nota: el autogenerate también detectó 2 operaciones de índice ajenas a este cambio
(`ix_contrato_estado_contrato` removido, `ix_marca_nombre_marca` agregado) — es la
deriva de índices de F0 ya documentada en `docs/modulos/f2-facturacion/f2-facturacion.md`
("Pendientes / dudas"), no relacionada con `regimen_fiscal`. Se excluyeron de esta
migración a propósito.

Revision ID: 7d5f9c4589c0
Revises: 5da59f306b51
Create Date: 2026-09-08 11:14:58.056292
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '7d5f9c4589c0'
down_revision: str | None = '5da59f306b51'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = ('empresa_facturadora', 'anunciante', 'agencia')


def upgrade() -> None:
    for tabla in _TABLAS:
        op.add_column(tabla, sa.Column('regimen_fiscal', sa.Unicode(length=4), nullable=True))


def downgrade() -> None:
    for tabla in reversed(_TABLAS):
        op.drop_column(tabla, 'regimen_fiscal')
