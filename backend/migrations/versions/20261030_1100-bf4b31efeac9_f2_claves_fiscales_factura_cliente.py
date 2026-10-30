"""f2 claves fiscales factura cliente

Agrega `clave_prod_serv`/`clave_unidad`/`moneda_sat`/`tipo_comprobante` (claves de
`ConstantesSistema`, sin FK formal — mismo patrón que `metodo_pago_clave`/
`forma_pago_clave`) a `FacturaCliente`.

Petición del usuario (ADR-223): el formulario de "Nueva factura" no capturaba estas 4
claves fiscales. `clave_prod_serv`/`clave_unidad` reemplazan el mecanismo viejo
(`_constante_unica`, "solo si hay una activa en el catálogo") por captura real, mismo
bug de fondo que `forma_pago_clave` (ADR-065 bis); `moneda_sat` reemplaza el default fijo
`"MXN"` que traía `DatosTimbrado.moneda`. `tipo_comprobante` se captura pero todavía no se
conecta al archivo plano del timbrador (ver nota junto a la columna en el modelo).

Columnas nullable: las facturas viejas nunca las capturaron y no se les inventa un valor;
`FacturaClienteCreate` las exige de aquí en adelante.

Revision ID: bf4b31efeac9
Revises: a1c4f6e8b2d7
Create Date: 2026-10-30 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'bf4b31efeac9'
down_revision: str | None = 'a1c4f6e8b2d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_cliente', sa.Column('clave_prod_serv', sa.Unicode(length=20), nullable=True)
    )
    op.add_column(
        'factura_cliente', sa.Column('clave_unidad', sa.Unicode(length=20), nullable=True)
    )
    op.add_column(
        'factura_cliente', sa.Column('moneda_sat', sa.Unicode(length=20), nullable=True)
    )
    op.add_column(
        'factura_cliente', sa.Column('tipo_comprobante', sa.Unicode(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('factura_cliente', 'tipo_comprobante')
    op.drop_column('factura_cliente', 'moneda_sat')
    op.drop_column('factura_cliente', 'clave_unidad')
    op.drop_column('factura_cliente', 'clave_prod_serv')
