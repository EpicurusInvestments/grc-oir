"""agrega motivo_cancelacion a pago_cliente (ADR-286)

Revision ID: 5782aa74d8d8
Revises: b7c8d9e0f1a2
Create Date: 2026-11-24 16:23:13.378068
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# identificadores de revisión, usados por Alembic.
revision: str = '5782aa74d8d8'
down_revision: str | None = 'b7c8d9e0f1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Revisado a mano: el autogenerate también detectó deriva preexistente, sin
    # relación con este cambio (log_envio_correo_orden_estacion, constantes_sistema,
    # contrato, marca, requisicion) — se descarta, solo queda la columna nueva.
    op.add_column('pago_cliente', sa.Column('motivo_cancelacion', sa.Unicode(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('pago_cliente', 'motivo_cancelacion')
