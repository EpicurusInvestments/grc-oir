"""Servicio genérico de catálogos (capa de negocio).

Envuelve `BaseRepository`, devuelve SIEMPRE el schema de salida (`XxxRead`, nunca el
modelo crudo) y expone puntos de extensión (`_pre_create`, `_pre_update`) donde las
subclases enchufan reglas de su entidad: fórmulas, `field_permissions.verificar` y
`audit.log_cambio_parametro` para los campos sensibles (lo usará F0-03).
"""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.errors import NotFoundError
from app.core.security import CurrentUser
from app.modules.catalogos.base_repository import BaseRepository, ModelType
from app.modules.catalogos.schemas import ListParams, Page

if TYPE_CHECKING:
    from app.core.audit import LogCambioParametroRead

CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
ReadSchemaType = TypeVar("ReadSchemaType", bound=BaseModel)


class BaseService(
    Generic[ModelType, CreateSchemaType, UpdateSchemaType, ReadSchemaType]
):
    #: Schema de salida; lo define la subclase (p.ej. `read_schema = PlazaRead`).
    read_schema: type[ReadSchemaType]
    #: Nombre de la entidad de la spec, para mensajes/auditoría (p.ej. "Plaza").
    entidad: str = "Catálogo"

    def __init__(self, repo: BaseRepository[ModelType]) -> None:
        self.repo = repo

    # ── conversión ────────────────────────────────────────────────────────────
    def _to_read(self, obj: ModelType) -> ReadSchemaType:
        return self.read_schema.model_validate(obj)

    # ── lectura ───────────────────────────────────────────────────────────────
    def list(self, params: ListParams) -> Page[ReadSchemaType]:
        items, total = self.repo.list(params)
        return Page[ReadSchemaType](
            items=[self._to_read(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def get(self, id_: Any) -> ReadSchemaType:
        return self._to_read(self._get_or_404(id_))

    def _get_or_404(self, id_: Any) -> ModelType:
        obj = self.repo.get(id_)
        if obj is None:
            raise NotFoundError(f"{self.entidad} no encontrado.", detalles={"id": str(id_)})
        return obj

    # ── escritura ─────────────────────────────────────────────────────────────
    def create(self, data: CreateSchemaType, usuario: CurrentUser) -> ReadSchemaType:
        payload = data.model_dump()
        self._pre_create(payload, usuario)
        return self._to_read(self.repo.create(payload))

    def update(
        self, id_: Any, data: UpdateSchemaType, usuario: CurrentUser
    ) -> ReadSchemaType:
        obj = self._get_or_404(id_)
        payload = data.model_dump(exclude_unset=True)
        self._pre_update(obj, payload, usuario)
        return self._to_read(self.repo.update(obj, payload))

    def cambiar_estado(
        self, id_: Any, activo: bool, usuario: CurrentUser, forzar: bool = False
    ) -> ReadSchemaType:
        obj = self._get_or_404(id_)
        if not activo:
            self._pre_desactivar(obj, forzar, usuario)
        return self._to_read(self.repo.set_activo(obj, activo))

    # ── auditoría (solo lectura del historial de ESTA entidad) ───────────────────
    # Nota: se anota con `Sequence` (no `list`) porque dentro de esta clase el nombre
    # `list` refiere al MÉTODO `list` de arriba, no al tipo builtin.
    def historial(self, id_: Any) -> Sequence[LogCambioParametroRead]:
        """Historial de cambios de parámetros sensibles de un registro (más reciente
        primero). Lectura acotada; la administración completa de auditoría es de F5."""
        from app.core import audit  # import diferido: evita acoplar la base con auditoría

        self._get_or_404(id_)  # 404 si el registro no existe
        return [
            audit.LogCambioParametroRead.model_validate(r)
            for r in audit.listar_historial(self.repo.db, self.entidad, id_)
        ]

    # ── puntos de extensión (las subclases los sobreescriben) ───────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        """Hook previo al alta. Aquí van fórmulas/validaciones de la entidad."""

    def _pre_update(
        self, obj: ModelType, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        """Hook previo a la edición.

        Aquí las subclases llaman a `field_permissions.verificar(...)` y
        `audit.log_cambio_parametro(...)` para los campos sensibles de su entidad.
        """

    def _pre_desactivar(
        self, obj: ModelType, forzar: bool, usuario: CurrentUser
    ) -> None:
        """Hook previo a la BAJA lógica (`activo=False`).

        Las subclases validan aquí que no existan dependientes activos y, si los hay y
        `forzar=False`, lanzan `DependenciasActivasError`. Por defecto no bloquea nada.
        """
