"""Pruebas de los catálogos operativos F0-01 (Plaza · Afiliado · Estación) sobre SQLite.

Se ejercitan las REGLAS de negocio (capa de servicio) sin depender de SQL Server / red:
selección libre de plaza en Estación (ADR-094, reemplaza a la herencia de ADR-005),
Afiliado sin plaza propia (ADR-096 — la plaza es propiedad de la Estación, no del
Afiliado), unicidad de RFC, validación de formato de RFC, tipo de señal y baja lógica
bloqueada por dependientes activos. El DDL real (UNIQUEIDENTIFIER, CHECK, índices) se
valida contra RDS con `alembic upgrade`, no aquí.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import mssql
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
from app.shared.base_repository import BaseRepository
from app.shared.schemas import ListParams

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
    plaza_svc = PlazaService(plaza_repo, estacion_repo=est_repo)
    afi_svc = AfiliadoService(afi_repo, estacion_repo=est_repo)
    est_svc = EstacionService(est_repo, afiliado_repo=afi_repo, plaza_repo=plaza_repo)
    return plaza_svc, afi_svc, est_svc


# ── helpers ─────────────────────────────────────────────────────────────────────
def _plaza(svc: PlazaService, nombre: str = "Monterrey", estado: str = "Nuevo León") -> PlazaRead:
    return svc.create(PlazaCreate(nombre_plaza=nombre, estado=estado), USUARIO)


def _afiliado(
    svc: AfiliadoService,
    rfc: str = "MEO850101OP2",
    nombre: str = "Multimedios",
) -> AfiliadoRead:
    return svc.create(
        AfiliadoCreate(
            nombre_afiliado=nombre,
            razon_social_afiliado=f"{nombre} SA de CV",
            rfc_afiliado=rfc,
        ),
        USUARIO,
    )


def _estacion(
    svc: EstacionService,
    afiliado_id: uuid.UUID,
    plaza_id: uuid.UUID,
    nombre: str = "XHMT-FM",
    tipo: str = "fm",
) -> EstacionRead:
    return svc.create(
        EstacionCreate(
            afiliado_id=afiliado_id,
            plaza_id=plaza_id,
            nombre_estacion=nombre,
            tipo_senal=TipoSenal(tipo),
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


# ── Estación: plaza de selección libre (ADR-094, reemplaza a ADR-005) ────────────
def test_estacion_captura_su_propia_plaza(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    est = _estacion(est_svc, afi.afiliado_id, plaza.plaza_id)
    assert est.plaza_id == plaza.plaza_id


def test_estacion_editar_reasigna_plaza(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza1 = _plaza(plaza_svc, "CDMX", "CDMX")
    plaza2 = _plaza(plaza_svc, "León", "Guanajuato")
    afi = _afiliado(afi_svc)
    est = _estacion(est_svc, afi.afiliado_id, plaza1.plaza_id)
    actualizado = est_svc.update(est.estacion_id, EstacionUpdate(plaza_id=plaza2.plaza_id), USUARIO)
    assert actualizado.plaza_id == plaza2.plaza_id


def test_estacion_plaza_inexistente_rechazada_en_alta(servicios: Servicios) -> None:
    _, afi_svc, est_svc = servicios
    afi = _afiliado(afi_svc)
    with pytest.raises(NotFoundError):
        _estacion(est_svc, afi.afiliado_id, uuid.uuid4())


def test_estacion_plaza_inexistente_rechazada_en_edicion(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    est = _estacion(est_svc, afi.afiliado_id, plaza.plaza_id)
    with pytest.raises(NotFoundError):
        est_svc.update(est.estacion_id, EstacionUpdate(plaza_id=uuid.uuid4()), USUARIO)


def test_estacion_siglas_opcional(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    creada = est_svc.create(
        EstacionCreate(
            afiliado_id=afi.afiliado_id,
            plaza_id=plaza.plaza_id,
            nombre_estacion="La Que Buena",
            siglas="XEW",
            tipo_senal=TipoSenal.FM,
        ),
        USUARIO,
    )
    assert creada.siglas == "XEW"
    sin_siglas = _estacion(est_svc, afi.afiliado_id, plaza.plaza_id, nombre="Sin siglas")
    assert sin_siglas.siglas is None


def test_estacion_afiliado_inexistente_falla(servicios: Servicios) -> None:
    plaza_svc, _, est_svc = servicios
    plaza = _plaza(plaza_svc)
    with pytest.raises(NotFoundError):
        _estacion(est_svc, uuid.uuid4(), plaza.plaza_id)


def test_estacion_incluye_afiliado_nombre_y_plaza_nombre(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc, "Monterrey", "Nuevo León")
    afi = _afiliado(afi_svc, nombre="OIR Bajío")
    est = _estacion(est_svc, afi.afiliado_id, plaza.plaza_id)
    assert est.afiliado_nombre == "OIR Bajío"
    assert est.plaza_nombre == "Monterrey"


def test_tipo_senal_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        EstacionCreate(afiliado_id=uuid.uuid4(), nombre_estacion="X", tipo_senal="xx")


def test_estacion_list_por_afiliado(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    otro = _afiliado(afi_svc, rfc="OIR920301AB1", nombre="Otro")
    _estacion(est_svc, afi.afiliado_id, plaza.plaza_id, nombre="XHMT-FM")
    _estacion(est_svc, afi.afiliado_id, plaza.plaza_id, nombre="XHMA-AM", tipo="am")
    _estacion(est_svc, otro.afiliado_id, plaza.plaza_id, nombre="XHLE-FM")

    page = est_svc.list_por_afiliado(afi.afiliado_id, ListParams())
    assert page.total == 2
    assert {e.nombre_estacion for e in page.items} == {"XHMT-FM", "XHMA-AM"}


# ── Afiliado: unicidad y formato de RFC ───────────────────────────────────────────
def test_rfc_duplicado_rechazado(servicios: Servicios) -> None:
    _, afi_svc, _ = servicios
    _afiliado(afi_svc, rfc="MEO850101OP2", nombre="Uno")
    with pytest.raises(ConflictError):
        _afiliado(afi_svc, rfc="MEO850101OP2", nombre="Dos")


def test_rfc_formato_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        AfiliadoCreate(
            nombre_afiliado="X",
            razon_social_afiliado="X SA",
            rfc_afiliado="NO-ES-RFC",
        )


def test_rfc_se_normaliza_a_mayusculas(servicios: Servicios) -> None:
    _, afi_svc, _ = servicios
    afi = afi_svc.create(
        AfiliadoCreate(
            nombre_afiliado="Uno",
            razon_social_afiliado="Uno SA",
            rfc_afiliado="meo850101op2",
        ),
        USUARIO,
    )
    assert afi.rfc_afiliado == "MEO850101OP2"


def test_update_rfc_a_uno_existente_rechazado(servicios: Servicios) -> None:
    _, afi_svc, _ = servicios
    _afiliado(afi_svc, rfc="MEO850101OP2", nombre="Uno")
    afi2 = _afiliado(afi_svc, rfc="OIR920301AB1", nombre="Dos")
    with pytest.raises(ConflictError):
        afi_svc.update(afi2.afiliado_id, AfiliadoUpdate(rfc_afiliado="MEO850101OP2"), USUARIO)


# ── Baja lógica con dependientes activos (E-2) ────────────────────────────────────
def test_afiliado_baja_bloqueada_con_estacion_activa(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    _estacion(est_svc, afi.afiliado_id, plaza.plaza_id)

    with pytest.raises(DependenciasActivasError):
        afi_svc.cambiar_estado(afi.afiliado_id, activo=False, usuario=USUARIO)

    forzado = afi_svc.cambiar_estado(afi.afiliado_id, activo=False, usuario=USUARIO, forzar=True)
    assert forzado.activo is False


def test_plaza_baja_permitida_sin_dependientes(servicios: Servicios) -> None:
    plaza_svc, _, _ = servicios
    plaza = _plaza(plaza_svc, "Puebla", "Puebla")
    baja = plaza_svc.cambiar_estado(plaza.plaza_id, activo=False, usuario=USUARIO)
    assert baja.activo is False


# ── Campos derivados: conteo de estaciones ────────────────────────────────────────
def test_plaza_incluye_conteo_estaciones(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    e1 = _estacion(est_svc, afi.afiliado_id, plaza.plaza_id, nombre="XHMT-FM")
    _estacion(est_svc, afi.afiliado_id, plaza.plaza_id, nombre="XHMA-AM", tipo="am")
    # Una inactiva IGUAL cuenta (mismo criterio que el HTML aprobado).
    est_svc.cambiar_estado(e1.estacion_id, activo=False, usuario=USUARIO)

    item = next(p for p in plaza_svc.list(ListParams()).items if p.plaza_id == plaza.plaza_id)
    assert item.estaciones_count == 2
    assert plaza_svc.get(plaza.plaza_id).estaciones_count == 2


def test_plaza_sin_estaciones_cuenta_cero(servicios: Servicios) -> None:
    plaza_svc, _, _ = servicios
    plaza = _plaza(plaza_svc, "Vacía", "X")
    assert plaza_svc.get(plaza.plaza_id).estaciones_count == 0


def test_afiliado_incluye_conteo_estaciones(servicios: Servicios) -> None:
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc, "Monterrey", "Nuevo León")
    afi = _afiliado(afi_svc)
    e1 = _estacion(est_svc, afi.afiliado_id, plaza.plaza_id, nombre="XHMT-FM")
    est_svc.cambiar_estado(e1.estacion_id, activo=False, usuario=USUARIO)  # inactiva cuenta

    item = next(a for a in afi_svc.list(ListParams()).items if a.afiliado_id == afi.afiliado_id)
    assert item.estaciones_count == 1

    leido = afi_svc.get(afi.afiliado_id)
    assert leido.estaciones_count == 1


# ── Portabilidad a SQL Server del filtro de "activo" (BIT) — regresión ADR-014 ────
def test_conteo_activas_desactivacion_funciona_por_dependientes(servicios: Servicios) -> None:
    """Ruta de desactivación con dependientes (dispara el conteo de estaciones activas).

    Cubre el flujo que en RDS fallaba por `.is_(True)`. En SQLite valida el comportamiento;
    la portabilidad del SQL a SQL Server la garantiza `test_filtro_activo_*` (abajo).
    """
    plaza_svc, afi_svc, est_svc = servicios
    plaza = _plaza(plaza_svc)
    afi = _afiliado(afi_svc)
    _estacion(est_svc, afi.afiliado_id, plaza.plaza_id)  # estación activa dependiente

    # Afiliado con estación activa → bloquea; con forzar procede.
    with pytest.raises(DependenciasActivasError):
        afi_svc.cambiar_estado(afi.afiliado_id, activo=False, usuario=USUARIO)
    assert (
        afi_svc.cambiar_estado(afi.afiliado_id, activo=False, usuario=USUARIO, forzar=True).activo
        is False
    )

    # Plaza con estación activa → bloquea; con forzar procede.
    plaza2 = _plaza(plaza_svc, "CDMX", "CDMX")
    afi2 = _afiliado(afi_svc, rfc="OIR920301AB1", nombre="Dos")
    _estacion(est_svc, afi2.afiliado_id, plaza2.plaza_id, nombre="XHRC-FM")
    with pytest.raises(DependenciasActivasError):
        plaza_svc.cambiar_estado(plaza2.plaza_id, activo=False, usuario=USUARIO)
    assert (
        plaza_svc.cambiar_estado(plaza2.plaza_id, activo=False, usuario=USUARIO, forzar=True).activo
        is False
    )


def test_filtro_activo_compila_para_sqlserver() -> None:
    """El filtro `activo == True` debe rendir `activo = 1` en SQL Server, nunca `IS 1`.

    `IS` en SQL Server solo compara con NULL; `.is_(True)` generaba SQL inválido (bug de
    producción que SQLite no detectaba). Este guard fija el criterio a nivel de dialecto.
    """
    stmt = (
        select(func.count()).select_from(Estacion).where(Estacion.activo == True)  # noqa: E712
    )
    dialecto = mssql.dialect()  # type: ignore[no-untyped-call]
    sql = str(stmt.compile(dialect=dialecto, compile_kwargs={"literal_binds": True}))
    assert "activo = 1" in sql
    assert "IS 1" not in sql and "IS 0" not in sql


def test_sin_is_true_false_en_catalogos() -> None:
    """Guard: prohíbe reintroducir `.is_(True)`/`.is_(False)` sobre columnas BIT en los
    módulos de catálogos (no es portable a SQL Server). Ver ADR-014."""
    import app.modules.catalogos as pkg

    base = Path(pkg.__file__).resolve().parent
    ofensores = [
        f.name
        for f in base.glob("*.py")
        if ".is_(True)" in f.read_text(encoding="utf-8")
        or ".is_(False)" in f.read_text(encoding="utf-8")
    ]
    assert not ofensores, f"Usar `== True/False` (no `.is_`) sobre BIT: {ofensores}"
