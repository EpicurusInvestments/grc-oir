"""f2 forma pago clave factura cliente

Agrega `forma_pago_clave` (clave SAT c_FormaPago, sugerida desde `ConstantesSistema`
grupo FormaPago, sin FK formal — mismo patrón que `metodo_pago_clave`) a
`FacturaCliente`.

Bug real (ADR-065 bis): `AGREGADOS.MedioPago` del layout del PAC nunca se capturaba por
factura — `_datos_timbrado()` lo resolvía solo con `_constante_unica("FormaPago")`
("exactamente una activa o falta"), que dejó de servir en cuanto ese catálogo tuvo más
de una activa. A diferencia de `RegimenFiscal`/`UsoCFDI` (ADR-065), esto no era una
sugerencia con default: era el ÚNICO capturable, y no lo era. Se corrige capturándolo
por factura, igual que `MetodoPago` (que sí se capturaba desde siempre).

Columna nullable: las facturas viejas nunca la capturaron y no se les inventa un valor;
`FacturaClienteCreate.forma_pago_clave` es obligatorio de aquí en adelante.

Nota: el autogenerate volvió a detectar las 2 operaciones de índice ajenas a este cambio
(`ix_contrato_estado_contrato` removido, `ix_marca_nombre_marca` agregado) — es la
deriva de índices de F0 ya documentada en `docs/modulos/f2-facturacion/f2-facturacion.md`
("Pendientes / dudas"), no relacionada con `forma_pago_clave`. Se excluyeron de esta
migración a propósito (mismo criterio que las 2 migraciones anteriores de ADR-065).

Revision ID: a9b3cdeef9e7
Revises: ebdf80f59dd1
Create Date: 2026-09-08 12:42:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a9b3cdeef9e7'
down_revision: str | None = 'ebdf80f59dd1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_cliente', sa.Column('forma_pago_clave', sa.Unicode(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('factura_cliente', 'forma_pago_clave')
