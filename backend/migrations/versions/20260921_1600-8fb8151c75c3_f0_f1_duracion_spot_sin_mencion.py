"""f0 f1 duracion spot sin mencion

ADR-098 (petición del usuario): se retira `mencion` del enum compartido `DuracionSpot`
(`app/shared/enums.py`, ADR-032) — desde ADR-097, "Mención" ya es un valor del campo
`producto` de `TarifaPlaza` (junto con spot/control_remoto/patrocinio); tenerlo también
como una "duración de spot" era conceptualmente redundante (una mención no dura 20/30/60
segundos). Afecta a las TRES tablas que comparten el enum: `tarifa_plaza` (F0-02),
`orden_cliente` y `orden_estacion` (F1) — se ajusta el CHECK constraint de cada una para
ya no aceptar `'mencion'`.

Sin filas afectadas: se verificó contra RDS (`GRC-OIR`) que ninguna de las tres tablas
tiene una fila con `duracion_spot = 'mencion'` — sin datos que migrar.

Revision ID: 8fb8151c75c3
Revises: 96798afba3cc
Create Date: 2026-09-21 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '8fb8151c75c3'
down_revision: str | None = '96798afba3cc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = (
    ('tarifa_plaza', 'ck_tarifa_plaza_duracion_spot'),
    ('orden_cliente', 'ck_orden_cliente_duracion_spot'),
    ('orden_estacion', 'ck_orden_estacion_duracion_spot'),
)


def upgrade() -> None:
    for tabla, nombre in _TABLAS:
        if op.get_bind().dialect.name == 'sqlite':
            with op.batch_alter_table(tabla) as batch:
                batch.drop_constraint(nombre, type_='check')
                batch.create_check_constraint(nombre, "duracion_spot IN ('20s', '30s', '60s')")
        else:
            op.drop_constraint(nombre, tabla, type_='check')
            op.create_check_constraint(nombre, tabla, "duracion_spot IN ('20s', '30s', '60s')")


def downgrade() -> None:
    for tabla, nombre in _TABLAS:
        if op.get_bind().dialect.name == 'sqlite':
            with op.batch_alter_table(tabla) as batch:
                batch.drop_constraint(nombre, type_='check')
                batch.create_check_constraint(
                    nombre, "duracion_spot IN ('20s', '30s', '60s', 'mencion')"
                )
        else:
            op.drop_constraint(nombre, tabla, type_='check')
            op.create_check_constraint(
                nombre, tabla, "duracion_spot IN ('20s', '30s', '60s', 'mencion')"
            )
