"""Pruebas F0-03 · Contrato (SQLite).

Cubren las reglas de servicio sin depender de SQL Server / red:
- validación de anunciante y de `fecha_fin >= fecha_inicio` (schema y servicio);
- `created_by` y `archivo_contrato_path` (prefijo S3 vía puerto de almacenamiento);
- **máquina de estados** `estado_contrato` (transiciones válidas e inválidas, idempotencia);
- **auditoría de `porcentaje_comision_contrato`** (sensible, nullable): alta con valor,
  edición con motivo, sin motivo → 400, no-Admin → 403, y NO auditar cuando el % es None;
- enriquecimiento `anunciante_nombre`.

El DDL real se valida contra RDS con `alembic upgrade`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import LogCambioParametro
from app.core.db import Base
from app.core.errors import DomainError, NotFoundError, PermissionDeniedError, StateTransitionError
from app.core.security import Area, CurrentUser
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import (
    Anunciante,
    AnuncianteCreate,
    AnuncianteRepository,
    AnuncianteService,
    Marca,
    MarcaRepository,
)
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.contrato import (
    Contrato,
    ContratoCreate,
    ContratoListParams,
    ContratoRead,
    ContratoRepository,
    ContratoService,
    ContratoUpdate,
    EstadoContrato,
)

ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")
VENTAS = CurrentUser(username="vendedor", area=Area.VENTAS, ip="127.0.0.1")


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def svc(db: Session) -> ContratoService:
    repo = ContratoRepository(
        db, Contrato, search_columns=[Contrato.numero_contrato, Contrato.nombre_contrato]
    )
    return ContratoService(
        repo, anunciante_repo=BaseRepository(db, Anunciante), almacenamiento=AlmacenamientoLocal()
    )


@pytest.fixture
def anunciante_id(db: Session) -> uuid.UUID:
    svc = AnuncianteService(
        AnuncianteRepository(db, Anunciante),
        agencia_repo=BaseRepository(db, Agencia),
        marca_repo=MarcaRepository(db, Marca),
        contrato_repo=ContratoRepository(db, Contrato),
    )
    a = svc.create(
        AnuncianteCreate(
            nombre_comercial="Refrescos",
            nombre_fiscal="Refrescos SA de CV",
            rfc_anunciante="RSA950101AB1",
        ),
        ADMIN,
    )
    return a.anunciante_id


# ── helpers ───────────────────────────────────────────────────────────────────
def _contrato(
    svc: ContratoService,
    anunciante_id: uuid.UUID,
    *,
    numero: str = "C-2026-001",
    comision: str | None = None,
    desde: date = date(2026, 1, 1),
    hasta: date = date(2026, 12, 31),
    usuario: CurrentUser = ADMIN,
) -> ContratoRead:
    return svc.create(
        ContratoCreate(
            anunciante_id=anunciante_id,
            numero_contrato=numero,
            nombre_contrato="Campaña anual",
            fecha_inicio_contrato=desde,
            fecha_fin_contrato=hasta,
            porcentaje_comision_contrato=Decimal(comision) if comision is not None else None,
        ),
        usuario,
    )


def _logs(db: Session) -> list[LogCambioParametro]:
    stmt = select(LogCambioParametro).where(
        LogCambioParametro.campo == "porcentaje_comision_contrato"
    )
    return list(db.scalars(stmt).all())


# ── Alta / validaciones ───────────────────────────────────────────────────────
def test_alta_basica(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id)
    assert c.estado_contrato == EstadoContrato.VIGENTE
    assert c.created_by == "tester"
    assert c.anunciante_nombre == "Refrescos"


def test_anunciante_inexistente_rechazado(svc: ContratoService) -> None:
    with pytest.raises(NotFoundError):
        _contrato(svc, uuid.uuid4())


def test_fecha_fin_menor_rechazada_en_schema() -> None:
    with pytest.raises(ValidationError):
        ContratoCreate(
            anunciante_id=uuid.uuid4(),
            numero_contrato="C-1",
            nombre_contrato="X",
            fecha_inicio_contrato=date(2026, 12, 31),
            fecha_fin_contrato=date(2026, 1, 1),
        )


def test_fecha_fin_menor_rechazada_en_update_parcial(
    svc: ContratoService, anunciante_id: uuid.UUID
) -> None:
    c = _contrato(svc, anunciante_id, desde=date(2026, 6, 1), hasta=date(2026, 12, 31))
    with pytest.raises(DomainError):
        svc.update(c.contrato_id, ContratoUpdate(fecha_fin_contrato=date(2026, 1, 1)), ADMIN)


# ── archivo_contrato_path (prefijo S3) ────────────────────────────────────────────
def test_archivo_path_es_prefijo_del_numero(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id, numero="C-2026-001")
    assert c.archivo_contrato_path == "contratos/C-2026-001/"


def test_archivo_path_se_recalcula_al_cambiar_numero(
    svc: ContratoService, anunciante_id: uuid.UUID
) -> None:
    c = _contrato(svc, anunciante_id, numero="C-2026-001")
    upd = svc.update(c.contrato_id, ContratoUpdate(numero_contrato="C-2026-999"), ADMIN)
    assert upd.archivo_contrato_path == "contratos/C-2026-999/"


# ── Máquina de estados ────────────────────────────────────────────────────────────
def test_transicion_valida(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id)
    susp = svc.transicionar_estado(c.contrato_id, EstadoContrato.SUSPENDIDO, ADMIN)
    assert susp.estado_contrato == EstadoContrato.SUSPENDIDO
    vig = svc.transicionar_estado(c.contrato_id, EstadoContrato.VIGENTE, ADMIN)
    assert vig.estado_contrato == EstadoContrato.VIGENTE


def test_transicion_invalida_rechazada(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id)
    svc.transicionar_estado(c.contrato_id, EstadoContrato.FINALIZADO, ADMIN)
    # finalizado solo permite → cancelado; volver a vigente no es válido.
    with pytest.raises(StateTransitionError):
        svc.transicionar_estado(c.contrato_id, EstadoContrato.VIGENTE, ADMIN)


def test_cualquiera_a_cancelado(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id)
    svc.transicionar_estado(c.contrato_id, EstadoContrato.FINALIZADO, ADMIN)
    canc = svc.transicionar_estado(c.contrato_id, EstadoContrato.CANCELADO, ADMIN)
    assert canc.estado_contrato == EstadoContrato.CANCELADO
    # cancelado es terminal.
    with pytest.raises(StateTransitionError):
        svc.transicionar_estado(c.contrato_id, EstadoContrato.VIGENTE, ADMIN)


def test_transicion_mismo_estado_idempotente(
    svc: ContratoService, anunciante_id: uuid.UUID
) -> None:
    c = _contrato(svc, anunciante_id)
    igual = svc.transicionar_estado(c.contrato_id, EstadoContrato.VIGENTE, ADMIN)
    assert igual.estado_contrato == EstadoContrato.VIGENTE


# ── Auditoría de porcentaje_comision_contrato (sensible, nullable) ────────────────
def test_alta_sin_comision_no_audita(
    svc: ContratoService, anunciante_id: uuid.UUID, db: Session
) -> None:
    _contrato(svc, anunciante_id, comision=None)
    assert len(_logs(db)) == 0  # sin override → nada sensible que auditar


def test_alta_con_comision_audita(
    svc: ContratoService, anunciante_id: uuid.UUID, db: Session
) -> None:
    c = _contrato(svc, anunciante_id, comision="8.5")
    logs = _logs(db)
    assert len(logs) == 1
    assert logs[0].entidad == "Contrato"
    assert logs[0].entidad_id == str(c.contrato_id)
    assert logs[0].valor_anterior is None
    assert logs[0].valor_nuevo == "8.5"


def test_editar_comision_con_motivo_audita(
    svc: ContratoService, anunciante_id: uuid.UUID, db: Session
) -> None:
    c = _contrato(svc, anunciante_id, comision="8")
    svc.update(
        c.contrato_id,
        ContratoUpdate(porcentaje_comision_contrato=Decimal("9.25"), motivo_cambio="Ajuste"),
        ADMIN,
    )
    logs = _logs(db)
    assert len(logs) == 2
    edicion = [log for log in logs if log.valor_anterior is not None][0]
    assert edicion.valor_anterior == "8.00"
    assert edicion.valor_nuevo == "9.25"
    assert edicion.motivo_cambio == "Ajuste"


def test_editar_comision_sin_motivo_rechazado(
    svc: ContratoService, anunciante_id: uuid.UUID
) -> None:
    c = _contrato(svc, anunciante_id, comision="8")
    with pytest.raises(DomainError):
        svc.update(c.contrato_id, ContratoUpdate(porcentaje_comision_contrato=Decimal("9")), ADMIN)


def test_editar_comision_no_admin_rechazado(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id, comision="8")
    with pytest.raises(PermissionDeniedError):
        svc.update(
            c.contrato_id,
            ContratoUpdate(porcentaje_comision_contrato=Decimal("9"), motivo_cambio="x"),
            VENTAS,
        )


def test_baja_logica(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    c = _contrato(svc, anunciante_id)
    baja = svc.cambiar_estado(c.contrato_id, activo=False, usuario=ADMIN)
    assert baja.activo is False
    # estado_contrato es independiente de activo.
    assert baja.estado_contrato == EstadoContrato.VIGENTE


def test_listar_por_anunciante(svc: ContratoService, anunciante_id: uuid.UUID) -> None:
    _contrato(svc, anunciante_id, numero="C-1")
    _contrato(svc, anunciante_id, numero="C-2")
    propios = svc.list(ContratoListParams(anunciante_id=anunciante_id))
    assert propios.total == 2
    # Otro anunciante (inexistente) no ve estos contratos.
    ajenos = svc.list(ContratoListParams(anunciante_id=uuid.uuid4()))
    assert ajenos.total == 0
