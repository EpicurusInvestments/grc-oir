"""f0 domicilio estructurado agencia

ADR-175 (petición del usuario): agrega el domicilio ESTRUCTURADO (10 campos, mismo
mecanismo que ADR-059 ya agregó a Anunciante/EmpresaFacturadora — autocompletado por
código postal contra `asentamiento_postal`) a `Agencia`. ADR-060 había dejado
explícitamente pendiente este caso ("Agencia TODAVÍA no tiene domicilio estructurado").

Agencia no tenía ningún campo de domicilio antes (ni uno legado tipo `localizacion`),
así que no hay nada que preservar — 10 columnas nuevas, nullable.

Revision ID: b8abcebf5d8b
Revises: 2d68ec72846c
Create Date: 2026-10-08 10:39:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'b8abcebf5d8b'
down_revision: str | None = '2d68ec72846c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mismo set de 10 columnas que ADR-059 agregó a anunciante/empresa_facturadora.
_COLUMNAS: list[tuple[str, sa.types.TypeEngine]] = [
    ('calle', sa.Unicode(length=150)),
    ('numero_exterior', sa.Unicode(length=20)),
    ('numero_interior', sa.Unicode(length=20)),
    ('colonia', sa.Unicode(length=150)),
    ('localidad', sa.Unicode(length=150)),
    ('referencia_domicilio', sa.Unicode(length=250)),
    ('municipio', sa.Unicode(length=150)),
    ('estado', sa.Unicode(length=100)),
    ('pais', sa.Unicode(length=3)),
    ('codigo_postal', sa.Unicode(length=5)),
]


def upgrade() -> None:
    for nombre, tipo in _COLUMNAS:
        op.add_column('agencia', sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    for nombre, _tipo in reversed(_COLUMNAS):
        op.drop_column('agencia', nombre)
