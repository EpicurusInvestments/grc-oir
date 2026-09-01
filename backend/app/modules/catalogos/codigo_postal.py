"""Catálogo AsentamientoPostal (F0) — códigos postales de México (SEPOMEX).

Referencia geográfica para autocompletar domicilios estructurados (Anunciante,
EmpresaFacturadora — ver esos módulos): dado un código postal puede haber VARIAS
colonias/asentamientos (`asentamiento`) — el usuario elige la que busca y el resto de
los campos (municipio, estado, ciudad) se llenan solos. `calle`/`numero_exterior`/
`numero_interior`/`referencia` NO están aquí: SEPOMEX no baja a ese nivel de detalle,
siempre se capturan a mano.

Es de SOLO LECTURA desde la API: no hay alta/edición/baja manual, se siembra completo
desde `backend/scripts/cargar_codigos_postales.py` a partir del catálogo público de
Correos de México (`backend/app/data/sepomex_codigos_postales.csv`, abril 2016 — ver
el README de esa carpeta para la fuente y cómo actualizarlo). Por eso no hay
`activo`/RBAC de escritura: nadie lo captura a mano, solo se lee.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Unicode, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.security import CurrentUser, requiere_permiso


class AsentamientoPostal(Base):
    __tablename__ = "asentamiento_postal"

    asentamiento_postal_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # Indexado, NO único: un mismo CP normalmente tiene varias colonias.
    codigo_postal: Mapped[str] = mapped_column(Unicode(5), index=True)
    asentamiento: Mapped[str] = mapped_column(Unicode(150))
    tipo_asentamiento: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    municipio: Mapped[str] = mapped_column(Unicode(150))
    estado: Mapped[str] = mapped_column(Unicode(100))
    ciudad: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    pais: Mapped[str] = mapped_column(Unicode(3), default="MEX")
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class AsentamientoPostalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo_postal: str
    asentamiento: str
    tipo_asentamiento: str | None = None
    municipio: str
    estado: str
    ciudad: str | None = None
    pais: str = "MEX"


router = APIRouter(prefix="/codigos-postales", tags=["catalogos:codigos_postales"])


@router.get("/{codigo_postal}", response_model=list[AsentamientoPostalRead])
def buscar_codigo_postal(
    codigo_postal: str,
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    db: Session = Depends(get_db),
) -> list[AsentamientoPostalRead]:
    """Colonias/asentamientos de un CP. Puede haber más de una (o ninguna, si el CP no
    existe en el catálogo o aún no se sembró) — el front las ofrece en un selector y
    llena el resto de los campos con la que el usuario elija; si no hay resultados,
    la captura sigue siendo manual."""
    filas = db.scalars(
        select(AsentamientoPostal)
        .where(AsentamientoPostal.codigo_postal == codigo_postal.strip())
        .order_by(AsentamientoPostal.asentamiento)
    ).all()
    return [AsentamientoPostalRead.model_validate(f) for f in filas]
