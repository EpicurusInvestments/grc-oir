"""Modelo de Usuario (F0-04, ampliado en F5-00).

F0-04 creó la tabla + un seed mínimo (1 admin) para que el RBAC tuviera un registro real
al que empatar. **F5-00** la conecta al login: `get_current_user` ya resuelve contra esta
tabla y se agrega `password_hash`.

- `area` es el ENUM de la spec, con los mismos valores que `core.security.Area`
  (ventas│facturacion│tesoreria│cxc│cxp│direccion│nominas│admin): VARCHAR + CHECK nombrado.
- `email` único (decisión E-3); desde F5-00 es además la **credencial de login** (H-2).
- `roles_adicionales` es texto libre (decisión E-5), reservado para el RBAC fino de F5.
- Se mantienen los 7 campos de la spec (sin `updated_at`; decisión E-6 / ADR-023). El
  rastro de quién cambió qué se lleva en `LogCambioParametro`, no en columnas nuevas.
- `password_hash` (F5-00) es el ÚNICO campo añadido fuera de la spec: es infraestructura
  de autenticación, no un dato de negocio. NUNCA se expone en un schema de lectura.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, datetime2
from app.core.security import Area

# CHECK de `area` derivado de la fuente única `core.security.Area` (mismos valores).
_AREAS_SQL = ", ".join(f"'{a.value}'" for a in Area)


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (CheckConstraint(f"area IN ({_AREAS_SQL})", name="ck_usuario_area"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_usuario: Mapped[str] = mapped_column(Unicode(160))
    email: Mapped[str] = mapped_column(Unicode(160), unique=True, index=True)
    area: Mapped[str] = mapped_column(Unicode(20))
    roles_adicionales: Mapped[str | None] = mapped_column(Unicode(400), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # F5-00 — hash de la contraseña (bcrypt). NULLABLE a propósito:
    #   (1) la fila `dev.admin` sembrada en F0-04 ya existía sin contraseña;
    #   (2) un usuario de Azure AD (futuro) nunca tendrá hash local.
    # Sin hash → no puede iniciar sesión (fail-closed). 255 deja margen para migrar a
    # argon2id (~97 chars) sin ALTER; bcrypt ocupa 60.
    password_hash: Mapped[str | None] = mapped_column(Unicode(255), default=None)
