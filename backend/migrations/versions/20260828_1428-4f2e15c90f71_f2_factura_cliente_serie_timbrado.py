"""f2 factura_cliente serie_timbrado

Agrega `factura_cliente.serie_timbrado` NVARCHAR(50) NULL: serie/número del certificado
de sello digital (CSD) que a veces devuelve el timbrador externo junto al folio fiscal y
la fecha de timbrado (mismo grupo de datos que captura ADR-047/`TimbrarIn`). Sin normativa
fija de formato en la spec BD v2 (no está ahí) — desviación aditiva del mismo tipo que
`layout_factura`/`metodo_pago_clave` documentadas en la migración F2 original
(`3e57e45d24cb`): texto libre nullable, sin catálogo propio.

Pedido del equipo tras revisar la pantalla de "Registrar timbrado" contra el prototipo
aprobado (ADR-051): el campo "Serie / certificado" del prototipo no tenía dónde
persistirse — se agrega aquí en vez de dejarlo solo en el formulario sin guardarse.

Revision ID: 4f2e15c90f71
Revises: 3e57e45d24cb
Create Date: 2026-08-28 14:28:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '4f2e15c90f71'
down_revision: str | None = '3e57e45d24cb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_cliente',
        sa.Column('serie_timbrado', sa.Unicode(length=50), nullable=True),
    )


def downgrade() -> None:
    # NULL, sin default constraint → drop directo (mismo criterio que otras columnas
    # aditivas nullable de este proyecto, p.ej. `usuario.password_hash`).
    op.drop_column('factura_cliente', 'serie_timbrado')
