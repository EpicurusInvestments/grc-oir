"""Repositorio genérico de catálogos (capa de datos).

ÚNICO punto que toca la BD para un catálogo simple. Cada catálogo de F0-01+ instancia
`BaseRepository(db, MiModelo, search_columns=[...])` y obtiene list/get/create/update y
cambio de estado sin reescribir SQL.

Convenciones de la spec: baja LÓGICA por la columna `activo` (nunca DELETE físico).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, func, inspect, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.db import Base
from app.modules.catalogos.schemas import ListParams

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(
        self,
        db: Session,
        model: type[ModelType],
        *,
        search_columns: Sequence[InstrumentedAttribute[Any]] | None = None,
        default_order_by: Sequence[InstrumentedAttribute[Any]] | None = None,
    ) -> None:
        self.db = db
        self.model = model
        self.search_columns = list(search_columns or [])
        # Orden estable para que la paginación sea determinista. Fallback a la PK.
        self.default_order_by = list(default_order_by or self._primary_key_columns())

    def _primary_key_columns(self) -> list[InstrumentedAttribute[Any]]:
        mapper = inspect(self.model)
        return [getattr(self.model, str(col.key)) for col in mapper.primary_key]

    def get(self, id_: Any) -> ModelType | None:
        return self.db.get(self.model, id_)

    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        if params.activo is not None:
            stmt = stmt.where(self.model.activo == params.activo)  # type: ignore[attr-defined]
        if params.q and self.search_columns:
            patron = f"%{params.q.strip()}%"
            condiciones: list[ColumnElement[bool]] = [
                col.ilike(patron) for col in self.search_columns
            ]
            stmt = stmt.where(or_(*condiciones))
        return stmt

    def list(self, params: ListParams) -> tuple[Sequence[ModelType], int]:
        base = self._apply_filters(select(self.model), params)
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.order_by(*self.default_order_by)
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        )
        items = self.db.scalars(stmt).all()
        return items, int(total)

    def create(self, data: dict[str, Any]) -> ModelType:
        obj = self.model(**data)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: ModelType, data: dict[str, Any]) -> ModelType:
        for campo, valor in data.items():
            setattr(obj, campo, valor)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def set_activo(self, obj: ModelType, activo: bool) -> ModelType:
        obj.activo = activo  # type: ignore[attr-defined]
        self.db.commit()
        self.db.refresh(obj)
        return obj
