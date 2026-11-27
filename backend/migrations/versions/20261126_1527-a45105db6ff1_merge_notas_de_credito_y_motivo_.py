"""merge notas de credito y motivo cancelacion

Revision ID: a45105db6ff1
Revises: d44def894ea8, e2f4a6b8c0d2
Create Date: 2026-11-26 15:27:17.172531
"""
from __future__ import annotations

from collections.abc import Sequence

# identificadores de revisión, usados por Alembic.
revision: str = 'a45105db6ff1'
down_revision: str | None = ('d44def894ea8', 'e2f4a6b8c0d2')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
