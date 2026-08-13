"""f5 00 password hash en usuario (login local)

F5-00 — Autenticación base:

- Agrega `usuario.password_hash` NVARCHAR(255) NULL: hash bcrypt de la contraseña.
  * NULLABLE a propósito: (1) la fila `dev.admin` sembrada en F0-04 ya existe sin
    contraseña; (2) los usuarios de Azure AD (futuro) nunca tendrán hash local.
  * 255 deja margen para migrar a argon2id (~97 chars) sin ALTER (bcrypt usa 60).
  * NUNCA se guarda la contraseña en claro, ni aquí ni en ningún otro lado.

- Asigna la contraseña inicial del seed `dev.admin` (id determinista de F0-04) tomando
  el valor SOLO del ENTORNO, nunca del repositorio:
      SEED_ADMIN_PASSWORD_HASH  → hash ya calculado (tiene prioridad), o
      SEED_ADMIN_PASSWORD       → contraseña en claro que esta migración hashea al vuelo.
  Si no se define ninguna, la columna queda NULL y `dev.admin` NO puede iniciar sesión
  hasta que un admin le establezca contraseña (fail-closed, sin contraseñas por defecto).
  Se cambia después desde la pantalla de gestión de usuarios (F5-00).

  Motivo de tomarla del entorno y no dejarla escrita aquí: la skill `migraciones-sqlserver`
  prohíbe secretos en migraciones, y un hash bcrypt versionado es atacable offline por
  cualquiera con acceso al repositorio.

Revision ID: a1c8e3d47b92
Revises: 73fa97f9e718
Create Date: 2026-08-12 10:00:00.000000

Nota de integración (2026-08-13): esta migración se creó colgando de `b6d9f2a4c817`
(F0-05), igual que la de F1 (`73fa97f9e718`), porque ambas ramas se desarrollaron en
paralelo. Al integrar F5-00 con F1 eso dejaba DOS cabezas y Alembic no puede migrar con
la cadena bifurcada, así que se re-encadenó ESTA (que aún no estaba en `main`) para que
cuelgue de la de F1: F0-05 → F1 → F5-00. La de F1 no se tocó: ya estaba publicada.

Las dos son conmutativas —F1 solo CREA las 6 tablas de órdenes y esta solo AGREGA una
columna a `usuario`—, así que el orden es una decisión de higiene del historial, no una
dependencia técnica. Las FK de F1 hacia `usuario.usuario_id` apuntan a la PK creada en
F0-04, antepasado común de ambas ramas.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# identificadores de revisión, usados por Alembic.
revision: str = 'a1c8e3d47b92'
down_revision: str | None = '73fa97f9e718'  # F1 (órdenes) — ver "Nota de integración"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mismo id determinista sembrado en F0-04 (revisión f1a4d0c25e63).
_SEED_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _hash_inicial() -> str | None:
    """Hash de la contraseña inicial del seed. SOLO del entorno; None si no se definió."""
    ya_hasheado = os.environ.get("SEED_ADMIN_PASSWORD_HASH", "").strip()
    if ya_hasheado:
        return ya_hasheado

    en_claro = os.environ.get("SEED_ADMIN_PASSWORD", "").strip()
    if en_claro:
        # Import diferido: el hashing vive en un solo lugar (app/core/auth/passwords.py),
        # así la migración y el login usan EXACTAMENTE el mismo algoritmo y parámetros.
        from app.core.auth.passwords import hash_password

        return hash_password(en_claro)

    return None


def upgrade() -> None:
    op.add_column(
        'usuario',
        sa.Column('password_hash', sa.Unicode(length=255), nullable=True),
    )

    hash_inicial = _hash_inicial()
    if hash_inicial:
        op.execute(
            sa.text("UPDATE usuario SET password_hash = :h WHERE usuario_id = :id").bindparams(
                sa.bindparam("h", hash_inicial, type_=sa.Unicode(length=255)),
                sa.bindparam("id", _SEED_ADMIN_ID, type_=sa.Uuid()),
            )
        )
    else:
        print(
            "[f5-00] SEED_ADMIN_PASSWORD / SEED_ADMIN_PASSWORD_HASH no definidos: "
            "'dev.admin' queda SIN contrasena y no podra iniciar sesion con "
            "AUTH_PROVIDER=local. Definelos en el .env y vuelve a aplicar, o establece la "
            "contrasena desde la pantalla de gestion de usuarios."
        )


def downgrade() -> None:
    # SQL Server: la columna es NULL y sin default constraint → drop directo.
    op.drop_column('usuario', 'password_hash')
