"""f0 constantes motivo cambio grupo

ADR-178 (petición del usuario): agrega el décimo grupo `MotivoCambio` al CHECK de
`constantes_sistema.grupo` (los 9 anteriores son SAT/timbrador). Es un catálogo NO fiscal
de motivos reutilizable por otras pantallas que piden un "motivo del cambio" en texto
libre (empieza por Tarifa, F0-02) — se agrupan por pantalla/sección dentro de este único
grupo. No cambia la unicidad `(grupo, clave)` a nivel BD: en este grupo la Clave se
captura con un sufijo numérico ya único (`CambioFecha_1`, `CambioFecha_2`...), calculado
en el servicio antes del INSERT (ver `ConstanteSistemaService._siguiente_clave_motivo_cambio`).

Ensanchar un CHECK existente requiere recrearlo — no hay `ALTER CONSTRAINT`. En SQLite,
`batch_alter_table` (no soporta `DROP/ADD CONSTRAINT` directo); en SQL Server,
`drop_constraint`/`create_check_constraint` sí funcionan en línea (ADR, ver
`migraciones-sqlserver`).

Revision ID: e92f9bc99f9f
Revises: 3bef064c9917
Create Date: 2026-10-09 22:56:55.691307
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'e92f9bc99f9f'
down_revision: str | None = '3bef064c9917'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GRUPOS_ANTES = (
    "grupo IN ('TipoComprobante', 'Serie', 'RegimenFiscal', 'ClaveProdServ', "
    "'ClaveUnidad', 'UsoCFDI', 'FormaPago', 'MetodoPago', 'MonedaSAT')"
)
_GRUPOS_DESPUES = (
    "grupo IN ('TipoComprobante', 'Serie', 'RegimenFiscal', 'ClaveProdServ', "
    "'ClaveUnidad', 'UsoCFDI', 'FormaPago', 'MetodoPago', 'MonedaSAT', 'MotivoCambio')"
)


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('constantes_sistema') as batch_op:
            batch_op.drop_constraint('ck_constantes_sistema_grupo', type_='check')
            batch_op.create_check_constraint('ck_constantes_sistema_grupo', _GRUPOS_DESPUES)
    else:
        op.drop_constraint('ck_constantes_sistema_grupo', 'constantes_sistema', type_='check')
        op.create_check_constraint(
            'ck_constantes_sistema_grupo', 'constantes_sistema', _GRUPOS_DESPUES
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('constantes_sistema') as batch_op:
            batch_op.drop_constraint('ck_constantes_sistema_grupo', type_='check')
            batch_op.create_check_constraint('ck_constantes_sistema_grupo', _GRUPOS_ANTES)
    else:
        op.drop_constraint('ck_constantes_sistema_grupo', 'constantes_sistema', type_='check')
        op.create_check_constraint(
            'ck_constantes_sistema_grupo', 'constantes_sistema', _GRUPOS_ANTES
        )
