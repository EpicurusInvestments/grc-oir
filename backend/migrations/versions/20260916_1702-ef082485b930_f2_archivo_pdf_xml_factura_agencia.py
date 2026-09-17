"""f2 archivo pdf xml factura agencia

ADR-079: FacturaAgencia sube su factura en PDF y XML por separado, mismo criterio que
ADR-070 en FacturaAfiliado. NULLABLE, sin `server_default` a propósito: un
`server_default` crea un DEFAULT CONSTRAINT en SQL Server que bloquea `DROP COLUMN` en
el downgrade (ver ADR-067/068) — no aplica aquí porque no se necesita un default.

Revision ID: ef082485b930
Revises: 19395aa1c258
Create Date: 2026-09-16 17:02:20.492010
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'ef082485b930'
down_revision: str | None = '19395aa1c258'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_agencia', sa.Column('archivo_pdf_path', sa.Unicode(length=500), nullable=True)
    )
    op.add_column(
        'factura_agencia', sa.Column('archivo_xml_path', sa.Unicode(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('factura_agencia', 'archivo_xml_path')
    op.drop_column('factura_agencia', 'archivo_pdf_path')
