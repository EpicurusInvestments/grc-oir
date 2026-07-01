"""Pruebas de la base genérica de catálogos (repository + service) sobre SQLite."""

from __future__ import annotations

import pytest

from app.core.errors import NotFoundError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.schemas import ListParams
from app.tests._demo import DemoCreate, DemoService, DemoUpdate

USUARIO = CurrentUser(username="tester", area=Area.ADMIN)


def _crear(svc: DemoService, nombre: str) -> str:
    return svc.create(DemoCreate(nombre=nombre), USUARIO).demo_id


def test_create_y_get(demo_service: DemoService) -> None:
    id_ = _crear(demo_service, "Plaza CDMX")
    leido = demo_service.get(id_)
    assert leido.nombre == "Plaza CDMX"
    assert leido.activo is True


def test_get_inexistente_lanza_404(demo_service: DemoService) -> None:
    with pytest.raises(NotFoundError):
        demo_service.get("no-existe")


def test_paginacion_por_pagina(demo_service: DemoService) -> None:
    for i in range(25):
        _crear(demo_service, f"Item {i:02d}")

    p1 = demo_service.list(ListParams(page=1, size=10))
    assert p1.total == 25
    assert p1.pages == 3
    assert len(p1.items) == 10

    p3 = demo_service.list(ListParams(page=3, size=10))
    assert len(p3.items) == 5


def test_filtro_activo_y_baja_logica(demo_service: DemoService) -> None:
    id_a = _crear(demo_service, "Activo")
    _crear(demo_service, "Otro activo")

    demo_service.cambiar_estado(id_a, activo=False, usuario=USUARIO)

    # La baja es lógica: el registro sigue existiendo.
    assert demo_service.get(id_a).activo is False

    inactivos = demo_service.list(ListParams(activo=False))
    assert inactivos.total == 1
    activos = demo_service.list(ListParams(activo=True))
    assert activos.total == 1
    todos = demo_service.list(ListParams(activo=None))
    assert todos.total == 2


def test_busqueda_texto(demo_service: DemoService) -> None:
    _crear(demo_service, "Monterrey")
    _crear(demo_service, "Guadalajara")

    res = demo_service.list(ListParams(q="monte"))  # case-insensitive
    assert res.total == 1
    assert res.items[0].nombre == "Monterrey"


def test_update(demo_service: DemoService) -> None:
    id_ = _crear(demo_service, "Nombre viejo")
    actualizado = demo_service.update(id_, DemoUpdate(nombre="Nombre nuevo"), USUARIO)
    assert actualizado.nombre == "Nombre nuevo"
