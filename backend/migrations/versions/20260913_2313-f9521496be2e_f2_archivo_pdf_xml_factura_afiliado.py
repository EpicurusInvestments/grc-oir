"""f2 archivo pdf xml factura afiliado

Agrega `archivo_pdf_path`/`archivo_xml_path` a `FacturaAfiliado`: la factura del afiliado
ahora se sube en PDF y XML por separado (mismo patrón que `FacturaCliente.xml_path`/
`pdf_path` — CLAVE de almacenamiento, sin columna de "nombre" aparte, se recupera del
propio ref). Ambas NULLABLE, sin `server_default` — no aplica el hallazgo de
ADR-067/068 (DEFAULT CONSTRAINT de SQL Server bloqueando `DROP COLUMN`): ese problema
solo aparece con `server_default`, que aquí no se usa.

Nota: el autogenerate también detectó las 2 operaciones de índice ajenas a este cambio
(`ix_contrato_estado_contrato` removido, `ix_marca_nombre_marca` agregado) — es la deriva
de índices de F0 ya documentada, no relacionada con este cambio. Se excluyeron a
propósito (mismo criterio que ADR-065/065 bis/067/068).

Revision ID: f9521496be2e
Revises: 00b9c6d6a5a1
Create Date: 2026-09-13 23:13:36.168812
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'f9521496be2e'
down_revision: str | None = '00b9c6d6a5a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_afiliado', sa.Column('archivo_pdf_path', sa.Unicode(length=500), nullable=True)
    )
    op.add_column(
        'factura_afiliado', sa.Column('archivo_xml_path', sa.Unicode(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('factura_afiliado', 'archivo_xml_path')
    op.drop_column('factura_afiliado', 'archivo_pdf_path')
