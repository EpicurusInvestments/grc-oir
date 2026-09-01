"""f0 domicilio estructurado anunciante empresa_facturadora

Agrega el domicilio ESTRUCTURADO (10 campos, igual a los grupos ExEmisorDomFiscal/
ExReceptorDomFiscal del layout del PAC) a `Anunciante` y `EmpresaFacturadora`, para
autocompletarlo por código postal (ver `asentamiento_postal`, migración anterior).

Desviación aditiva aprobada respecto a la spec BD v2 (mismo criterio que
`layout_factura`/`metodo_pago_clave` en F2, ADR-058/059): la spec define
`Anunciante.localizacion` y `EmpresaFacturadora.direccion_empresa` como texto libre
único. AMBOS quedan intactos (no se pierde lo ya capturado) — estas 10 columnas son
nuevas y nullable, la captura real desde ahora es con ellas.

Revision ID: eb36ee5c1a0d
Revises: 7f4db0ba33db
Create Date: 2026-08-31 17:35
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'eb36ee5c1a0d'
down_revision: str | None = '7f4db0ba33db'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = ('anunciante', 'empresa_facturadora')

# (nombre, tipo) — mismo set de 10 columnas en las 2 tablas.
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
    for tabla in _TABLAS:
        for nombre, tipo in _COLUMNAS:
            op.add_column(tabla, sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    for tabla in _TABLAS:
        for nombre, _tipo in reversed(_COLUMNAS):
            op.drop_column(tabla, nombre)
