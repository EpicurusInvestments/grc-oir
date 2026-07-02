"""Pruebas de los catálogos operativos F0-01 (Plaza · Afiliado · Estación) sobre SQLite.

Se ejercitan las REGLAS de negocio (capa de servicio) sin depender de SQL Server / red:
herencia de plaza, unicidad de RFC, validación de formato de RFC, tipo de señal y baja
lógica bloqueada por dependientes activos. El DDL real (UNIQUEIDENTIFIER, CHECK, índices)
se valida contra RDS con `alembic upgrade`, no aquí.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.errors import ConflictError, DependenciasActivasError, NotFoundError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.afiliado import (
    Afiliado,
    AfiliadoCreate,
    AfiliadoRead,
    AfiliadoRepository,
    AfiliadoService,
    AfiliadoUpdate,
)
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.estacion import (
    Estacion,
    EstacionCreate,
    EstacionRead,
    EstacionRepository,
    EstacionService,
    EstacionUpdate,
    TipoSenal,
)
from app.modules.catalogos.plaza import Plaza, PlazaCreate, PlazaRead, PlazaService
from app.modules.catalogos.schemas import ListParams

USUARIO = CurrentUser(username="tester", area=Area.ADMIN)

Servicios = tuple[PlazaService, AfiliadoService, EstacionService]


@pytest.fixture
def sqlite_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def servicios(sqlite_session: Session) -> tuple[PlazaService, AfiliadoService, EstacionService]:
    db = sqlite_session
    afi_repo = AfiliadoRepository(db, Afiliado)
    est_repo = EstacionRepository(db, Estacion)
    plaza_repo = BaseRepository(db, Plaza, search_columns=[Plaza.nombre_plaza])
    plaza_svc = PlazaService(plaza_repo, afiliado_repo=afi_repo, estacion_repo=est_repo)
    afi_svc = AfiliadoService(afi_repo, estacion_repo=est_repo)
    est_svc = EstacionService(est_repo, afiliado_repo=afi_repo)
    return plaza_svc, afi_svc, est_svc


# ── helpers ─────────────────────────────────────────────────────────────────────
def _plaza(
    svc: PlazaService, nombre: str = "Monterrey", estado: str = "Nuevo León"
) -> PlazaRead:
    return svc.create(PlazaCreate(nombre_plaza=nombre, estado=estado), USUARIO)


def _afiliado(
    svc: AfiliadoService,
    plaza_id: uuid.UUID,
    rfc: str = "MEO850101OP2",
    nombre: str = "Multimedios",
) -> AfiliadoRead:
    return svc.create(
        AfiliadoCreate(
            nombre_afiliado=nombre,
            razon_social_afiliado=f"{nombre} SA de CV",
            rfc_afiliado=rfc,
            plaza_id=plaza_id,
        ),
        USUARIO,
    )


def _estacion(
    svc: EstacionService,
    afiliado_id: uuid.UUID,
    nombre: str = "XHMT-FM",
    tipo: str = "fm",
) -> EstacionRead:
    return svc.create(
        EstacionCreate(
            afiliado_id=afiliado_id, nombre_estacion=nombre, tipo_senal=TipoSenal(tipo)
        ),
        USUARIO,
    )


# ── Plaza ────────────────────────────────────────────────────────────────────────
def test_plaza_crud(servicios: Servicios) -> None:
    plaza_svc, _, _ = servicios
    p = _plaza(plaza_svc, "CDMX", "Ciudad de México")
    assert p.nombre_plaza == "CDMX"
    assert p.activo is True
    assert plaza_svc.get(p.plaza_id).estado == "Ciudad de México"


# ── Estación: herencia de plaza (ADR-005) ─────────────────────────────────────────
def test_estacion_hereda_plaza_del_afiliado(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc, plaza.plaza_id)
    est = _estacion(est_svc, afi.afiliado_id)
    assert est.plaza_id == plaza.plaza_id


def test_estacion_recalcula_plaza_al_cambiar_afiliado(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza1 = _plaza(plaza_svc, "CDMX", "CDMX")
    plaza2 = _plaza(plaza_svc, "León", "Guanajuato")
    afi1 = _afiliado(afi_svc, plaza1.plaza_id, rfc="MEO850101OP2", nombre="Uno")
    afi2 = _afiliado(afi_svc, plaza2.plaza_id, rfc="OIR920301AB1", nombre="Dos")
    est = _estacion(est_svc, afi1.afiliado_id)
    actualizado = est_svc.update(
        est.estacion_id, EstacionUpdate(afiliado_id=afi2.afiliado_id), USUARIO
    )
    assert actualizado.plaza_id == plaza2.plaza_id


def test_estacion_afiliado_inexistente_falla(servicios: Servicios) -> None:
    _, _, est_svc = servicios
    with pytest.raises(NotFoundError):
        _estacion(est_svc, uuid.uuid4())


def test_tipo_senal_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        EstacionCreate(afiliado_id=uuid.uuid4(), nombre_estacion="X", tipo_senal="xx")


def test_estacion_list_por_afiliado(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc, plaza.plaza_id)
    otro = _afiliado(afi_svc, plaza.plaza_id, rfc="OIR920301AB1", nombre="Otro")
    _estacion(est_svc, afi.afiliado_id, nombre="XHMT-FM")
    _estacion(est_svc, afi.afiliado_id, nombre="XHMA-AM", tipo="am")
    _estacion(est_svc, otro.afiliado_id, nombre="XHLE-FM")

    page = est_svc.list_por_afiliado(afi.afiliado_id, ListParams())
    assert page.total == 2
    assert {e.nombre_estacion for e in page.items} == {"XHMT-FM", "XHMA-AM"}


# ── Afiliado: unicidad y formato de RFC ───────────────────────────────────────────
def test_rfc_duplicado_rechazado(servicios: Servicios) -> None:
    plaza_svc, afi_svc, _ = servicios
    plaza = _plaza(plaza_svc)
    _afiliado(afi_svc, plaza.plaza_id, rfc="MEO850101OP2", nombre="Uno")
    with pytest.raises(ConflictError):
        _afiliado(afi_svc, plaza.plaza_id, rfc="MEO850101OP2", nombre="Dos")


def test_rfc_formato_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        AfiliadoCreate(
            nombre_afiliado="X",
            razon_social_afiliado="X SA",
            rfc_afiliado="NO-ES-RFC",
            plaza_id=uuid.uuid4(),
        )


def test_rfc_se_normaliza_a_mayusculas(servicios: Servicios) -> None:
    plaza_svc, afi_svc, _ = servicios
    plaza = _plaza(plaza_svc)
    afi = afi_svc.create(
        AfiliadoCreate(
            nombre_afiliado="Uno",
            razon_social_afiliado="Uno SA",
            rfc_afiliado="meo850101op2",
            plaza_id=plaza.plaza_id,
        ),
        USUARIO,
    )
    assert afi.rfc_afiliado == "MEO850101OP2"


def test_update_rfc_a_uno_existente_rechazado(servicios: Servicios) -> None:
    plaza_svc, afi_svc, _ = servicios
    plaza = _plaza(plaza_svc)
    _afiliado(afi_svc, plaza.plaza_id, rfc="MEO850101OP2", nombre="Uno")
    afi2 = _afiliado(afi_svc, plaza.plaza_id, rfc="OIR920301AB1", nombre="Dos")
    with pytest.raises(ConflictError):
        afi_svc.update(afi2.afiliado_id, AfiliadoUpdate(rfc_afiliado="MEO850101OP2"), USUARIO)


# ── Baja lógica con dependientes activos (E-2) ────────────────────────────────────
def test_afiliado_baja_bloqueada_con_estacion_activa(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc, plaza.plaza_id)
    _estacion(est_svc, afi.afiliado_id)

    with pytest.raises(DependenciasActivasError):
        afi_svc.cambiar_estado(afi.afiliado_id, activo=False, usuario=USUARIO)

    forzado = afi_svc.cambiar_estado(afi.afiliado_id, activo=False, usuario=USUARIO, forzar=True)
    assert forzado.activo is False


def test_plaza_baja_bloqueada_con_afiliado_activo(servicios: Servicios) -> None:
    plaza_svc, afi_svc, _ = servicios
    plaza = _plaza(plaza_svc)
    _afiliado(afi_svc, plaza.plaza_id)  # afiliado activo, sin estaciones

    with pytest.raises(DependenciasActivasError):
        plaza_svc.cambiar_estado(plaza.plaza_id, activo=False, usuario=USUARIO)

    forzado = plaza_svc.cambiar_estado(plaza.plaza_id, activo=False, usuario=USUARIO, forzar=True)
    assert forzado.activo is False


def test_plaza_baja_permitida_sin_dependientes(servicios: Servicios) -> None:
    plaza_svc, _, _ = servicios
    plaza = _plaza(plaza_svc, "Puebla", "Puebla")
    baja = plaza_svc.cambiar_estado(plaza.plaza_id, activo=False, usuario=USUARIO)
    assert baja.activo is False
