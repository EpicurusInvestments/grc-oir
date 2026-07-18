"""Modelo base de Usuario (F0-04) — SOLO EL MODELO.

En F0 se crea la tabla + un seed mínimo (1 admin) para que el RBAC tenga un registro real
al que empatar. La **pantalla** de administración de usuarios/áreas y el cableado de
`get_current_user` contra esta tabla pertenecen a **F5** (seguridad).

- `area` es el ENUM de la spec, con los mismos valores que `core.security.Area`
  (ventas│facturacion│tesoreria│cxc│cxp│direccion│nominas│admin): VARCHAR + CHECK nombrado.
- `email` único (decisión E-3). `roles_adicionales` es texto libre (decisión E-5).
- Se mantiene EXACTAMENTE con los 7 campos de la spec (sin `updated_at`; decisión E-6).
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
    __table_args__ = (
        CheckConstraint(f"area IN ({_AREAS_SQL})", name="ck_usuario_area"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_usuario: Mapped[str] = mapped_column(Unicode(160))
    email: Mapped[str] = mapped_column(Unicode(160), unique=True, index=True)
    area: Mapped[str] = mapped_column(Unicode(20))
    roles_adicionales: Mapped[str | None] = mapped_column(Unicode(400), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
