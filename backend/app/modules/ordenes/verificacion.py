"""Verificacion (F1) — registro de lo realmente transmitido según el reporte del afiliado.

Tabla REAL persistida (spec BD v2) — revierte la decisión E.1 tomada para la demo de
frontend (ahí se modeló como vista derivada, sin haber leído todavía la spec real; queda
así documentado, no es un error, fue la mejor decisión posible con la información de
entonces).

La spec declara la relación `OrdenEstacion → Verificacion` (1:N) con FK a
`orden_estacion_id`. Aquí se ADAPTA esa FK para apuntar a `orden_estacion_dia_id`
(ADR-030): la propia spec autoriza granularidad por día ("se puede crear una
OrdenEstacion por fecha"), así que anclar la verificación al día es más fiel a esa lectura
que a la OrdenEstacion agrupada — y es lo que permite reconciliar/incidenciar día por día,
igual que la demo de frontend ya validó.

`reconciliada`: de solo escritura inicial en el código de HOY (confirmado: el único
lugar donde se asigna es el `Verificacion(...)` que construye
`OrdenEstacionService.avanzar_reales` — siempre `reconciliada=True`, literal, nunca
`False` — y ningún otro método la toca jamás).

**Hallazgo real de la auditoría de migración a RDS (Tanda 4): `reconciliada` es hoy un
campo MUERTO.** Si siempre vale `True` y nada lo lee para decidir algo (el cierre de la
OE no lo consulta; solo la existencia de las filas), no distingue nada — su propósito
en la spec (habilitar el cierre solo cuando se acepta la reconciliación) no se cumple:
el flujo real de 4 pasos de la spec (capturar realidad → revisar diferencias →
reconciliar → cerrar) se comprime en la práctica en una sola transacción atómica dentro
de `avanzar_reales`. No existe hoy un estado intermedio donde haya evidencia capturada
pero todavía no aceptada. **Esto es una decisión de negocio pendiente, no técnica — ver
pregunta abierta en la ficha del módulo y en ADR-037.**

**`updated_at` SÍ se agrega, con cambio de postura deliberado:** el argumento de
"registro inmutable, no necesita `updated_at`" solo se sostiene mientras el campo
`reconciliada` siga muerto. Si el negocio pide un flujo con verificaciones capturadas
pero no reconciliadas, `reconciliada` pasaría a ser mutable y la columna haría falta.
Agregarla ahora (nulable, sin uso — `onupdate` solo se dispara si algún día un
`UPDATE` real toca la fila) es una línea; agregarla después de aplicar a RDS es un
`ALTER TABLE` sobre una base compartida. Costo asimétrico: se agrega ahora aunque hoy
no la use nadie.

**Hueco conocido, sin resolver (no es parte del alcance de esta tanda):** si una
reconciliación se registró mal (spots verificados incorrectos, fecha equivocada), HOY
no existe ningún mecanismo para corregirla o revertirla — ni un endpoint de edición, ni
uno de borrado. La única vía sería una intervención directa en la base de datos, que no
es la práctica correcta para un sistema con RBAC/auditoría. Corregir esto requiere una
decisión de producto (¿se permite editar una Verificacion ya usada para cerrar una OE?
¿se anula y se crea una nueva, dejando rastro?) antes de construir el endpoint — queda
anotado en la ficha del módulo como pendiente.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.security import CurrentUser, requiere_permiso
from app.modules.ordenes.orden_estacion import OrdenEstacionDia
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


class Verificacion(Base):
    __tablename__ = "verificacion"
    __table_args__ = (
        # Auditoría de migración a RDS (Tanda 4): formaliza en el esquema lo que hoy
        # solo garantiza la máquina de estados de `avanzar_reales` (no puede correr dos
        # veces sobre la misma OE) — como máximo una Verificacion por día.
        UniqueConstraint("orden_estacion_dia_id", name="uq_verificacion_orden_estacion_dia"),
    )

    verificacion_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    orden_estacion_dia_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion_dia.orden_estacion_dia_id",
            name="fk_verificacion_orden_estacion_dia",
            ondelete="NO ACTION",
        )
    )
    spots_verificados: Mapped[int] = mapped_column()
    fecha_verificacion: Mapped[date] = mapped_column(fecha_sql())
    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    notas_verificacion: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    reconciliada: Mapped[bool] = mapped_column(default=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_verificacion_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # `updated_at` NULABLE, sin uso hoy (ver docstring): se agrega por el costo
    # asimétrico de no tenerla si `reconciliada` deja de ser un campo muerto.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schema de lectura (Tanda 3 — API de lectura; sin escritura: no es capturable, se
# genera al registrar el reporte del afiliado — Tanda 5) ─────────────────────────────
class VerificacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verificacion_id: uuid.UUID
    orden_estacion_dia_id: uuid.UUID
    spots_verificados: int
    fecha_verificacion: date
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    notas_verificacion: str | None = None
    reconciliada: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class VerificacionListParams(ListParams):
    """`ListParams` + filtros propios. Hereda `activo`, pero NUNCA se expone como query
    param: `Verificacion` no tiene baja lógica. Se hereda solo por compatibilidad de tipo
    con `BaseRepository`/`BaseService`."""

    orden_estacion_id: uuid.UUID | None = None  # vía JOIN con orden_estacion_dia
    reconciliada: bool | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class VerificacionRepository(BaseRepository[Verificacion]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`, columna
        # que Verificacion no tiene (no es de baja lógica).
        orden_estacion_id = getattr(params, "orden_estacion_id", None)
        if orden_estacion_id is not None:
            # JOIN con orden_estacion_dia: la vista "verificaciones de una OE" que usa el
            # frontend (VerificacionListPage) agrupa por OE, no por día (spec ancla la FK
            # de Verificacion al día — ver docstring del módulo).
            stmt = stmt.join(
                OrdenEstacionDia,
                Verificacion.orden_estacion_dia_id == OrdenEstacionDia.orden_estacion_dia_id,
            ).where(OrdenEstacionDia.orden_estacion_id == orden_estacion_id)
        reconciliada = getattr(params, "reconciliada", None)
        if reconciliada is not None:
            stmt = stmt.where(Verificacion.reconciliada == reconciliada)
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class VerificacionService(BaseService[Verificacion, BaseModel, BaseModel, VerificacionRead]):
    """Solo lectura: no es una entidad capturable (nace de registrar el reporte del
    afiliado — ver Tanda 5)."""

    read_schema = VerificacionRead
    entidad = "Verificacion"


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_verificacion_service(db: Session = Depends(get_db)) -> VerificacionService:
    return VerificacionService(VerificacionRepository(db, Verificacion))


router = APIRouter(prefix="/verificaciones", tags=["ordenes:verificaciones"])


@router.get("", response_model=Page[VerificacionRead])
def listar_verificaciones(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    orden_estacion_id: uuid.UUID | None = Query(
        None, description="Acota a las verificaciones (por día) de una OrdenEstacion"
    ),
    reconciliada: bool | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: VerificacionService = Depends(get_verificacion_service),
) -> Page[VerificacionRead]:
    return svc.list(
        VerificacionListParams(
            page=page, size=size, orden_estacion_id=orden_estacion_id, reconciliada=reconciliada
        )
    )


@router.get("/{item_id}", response_model=VerificacionRead)
def obtener_verificacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: VerificacionService = Depends(get_verificacion_service),
) -> VerificacionRead:
    return svc.get(item_id)
