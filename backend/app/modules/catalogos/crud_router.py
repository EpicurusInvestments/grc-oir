"""Factory de routers CRUD para catálogos (capa API).

`build_crud_router(...)` arma un `APIRouter` con los 5 endpoints estándar de un catálogo
(list paginado, get, create, update, cambio de estado), con `requiere_permiso` YA
cableado por acción. Así, dar de alta un catálogo en F0-01+ se reduce a:

    router = build_crud_router(
        prefix="/plazas", tags=["catalogos:plazas"], permiso_base="catalogos",
        read_schema=PlazaRead, create_schema=PlazaCreate, update_schema=PlazaUpdate,
        get_service=get_plaza_service,
    )

NOTA: este módulo evita `from __future__ import annotations` a propósito: necesita que
las anotaciones (p.ej. `payload: create_schema`) se evalúen al definir la función para
que FastAPI las reconozca como modelos de cuerpo.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.schemas import CambioEstadoIn, Page


def build_crud_router(
    *,
    prefix: str,
    tags: list[str],
    permiso_base: str,
    read_schema: type[Any],
    create_schema: type[Any],
    update_schema: type[Any],
    get_service: Callable[..., BaseService[Any, Any, Any, Any]],
    id_type: type[Any] = str,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)

    @router.get("", response_model=Page[read_schema])
    def listar(
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
        activo: bool | None = Query(None, description="None=todos, true=activos, false=inactivos"),
        q: str | None = Query(None, description="Búsqueda de texto"),
        usuario: CurrentUser = Depends(requiere_permiso(f"{permiso_base}:leer")),
        svc: BaseService[Any, Any, Any, Any] = Depends(get_service),
    ) -> Any:
        from app.modules.catalogos.schemas import ListParams

        return svc.list(ListParams(page=page, size=size, activo=activo, q=q))

    @router.get("/{item_id}", response_model=read_schema)
    def obtener(
        item_id: id_type,
        usuario: CurrentUser = Depends(requiere_permiso(f"{permiso_base}:leer")),
        svc: BaseService[Any, Any, Any, Any] = Depends(get_service),
    ) -> Any:
        return svc.get(item_id)

    @router.post("", response_model=read_schema, status_code=201)
    def crear(
        payload: create_schema,
        usuario: CurrentUser = Depends(requiere_permiso(f"{permiso_base}:crear")),
        svc: BaseService[Any, Any, Any, Any] = Depends(get_service),
    ) -> Any:
        return svc.create(payload, usuario)

    @router.put("/{item_id}", response_model=read_schema)
    def actualizar(
        item_id: id_type,
        payload: update_schema,
        usuario: CurrentUser = Depends(requiere_permiso(f"{permiso_base}:editar")),
        svc: BaseService[Any, Any, Any, Any] = Depends(get_service),
    ) -> Any:
        return svc.update(item_id, payload, usuario)

    @router.post("/{item_id}/estado", response_model=read_schema)
    def cambiar_estado(
        item_id: id_type,
        payload: CambioEstadoIn,
        usuario: CurrentUser = Depends(requiere_permiso(f"{permiso_base}:editar")),
        svc: BaseService[Any, Any, Any, Any] = Depends(get_service),
    ) -> Any:
        """Activa/desactiva (baja lógica). Nunca borra físicamente."""
        return svc.cambiar_estado(item_id, payload.activo, usuario)

    return router
