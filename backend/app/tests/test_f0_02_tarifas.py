"""Pruebas del catálogo F0-02 (TarifaPlaza) sobre SQLite.

Se ejercitan las REGLAS de negocio (capa de servicio) sin depender de SQL Server / red:
campo calculado `tarifa_neta`, detección de duplicado activo (ADR-097: reemplaza la
validación de solapamiento de vigencias, ahora eliminada), enriquecimiento con el nombre
de la estación referenciada y la dependencia de Estación. El DDL real (UNIQUEIDENTIFIER,
NUMERIC, CHECK, índices) se valida contra RDS con `alembic upgrade`, no aquí.

La portabilidad a SQL Server del filtro booleano se fija con un guard que compila la
consulta con el dialecto mssql (ver ADR-014).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, or_, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import LogCambioParametro
from app.core.db import Base
from app.core.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.tarifa import (
    ProductoTarifa,
    TarifaPlaza,
    TarifaPlazaCreate,
    TarifaPlazaRead,
    TarifaPlazaUpdate,
    TarifaRepository,
    TarifaService,
    TipoSenal,
    calcular_tarifa_neta,
)
from app.shared.base_repository import BaseRepository
from app.shared.enums import DuracionSpot
from app.shared.schemas import ListParams

USUARIO = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")
VENTAS = CurrentUser(username="vendedor", area=Area.VENTAS, ip="127.0.0.1")


def _logs(db: Session, campo: str | None = None) -> list[LogCambioParametro]:
    stmt = select(LogCambioParametro)
    if campo is not None:
        stmt = stmt.where(LogCambioParametro.campo == campo)
    return list(db.scalars(stmt).all())


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
def contexto(sqlite_session: Session) -> tuple[TarifaService, Estacion]:
    db = sqlite_session
    plaza_repo = BaseRepository(db, Plaza)
    estacion_repo = BaseRepository(db, Estacion)
    # Sin search_columns: la búsqueda `q` se resuelve con JOIN a estacion en _apply_filters.
    tarifa_repo = TarifaRepository(db, TarifaPlaza)
    svc = TarifaService(tarifa_repo, estacion_repo=estacion_repo)
    plaza = plaza_repo.create({"nombre_plaza": "CDMX", "estado": "Ciudad de México"})
    afiliado_repo = BaseRepository(db, Afiliado)
    afiliado = afiliado_repo.create(
        {
            "nombre_afiliado": "OIR Bajío",
            "razon_social_afiliado": "OIR Bajío SA de CV",
            "rfc_afiliado": "OIR920301AB1",
        }
    )
    estacion = estacion_repo.create(
        {
            "afiliado_id": afiliado.afiliado_id,
            "plaza_id": plaza.plaza_id,
            "nombre_estacion": "XHRC-FM",
            "tipo_senal": "fm",
        }
    )
    return svc, estacion


def _crear_estacion(svc: TarifaService, nombre: str, tipo_senal: str = "fm") -> Estacion:
    # El servicio expone su repo de estaciones; se usa para crear otra en pruebas. Necesita
    # afiliado y plaza propios — se resuelve directo contra la sesión del repo.
    db = svc._estacion_repo.db
    plaza_repo = BaseRepository(db, Plaza)
    afiliado_repo = BaseRepository(db, Afiliado)
    plaza = plaza_repo.create({"nombre_plaza": nombre, "estado": nombre})
    afiliado = afiliado_repo.create(
        {
            "nombre_afiliado": nombre,
            "razon_social_afiliado": f"{nombre} SA de CV",
            "rfc_afiliado": f"{nombre[:3].upper()}920301AB{len(nombre) % 10}",
        }
    )
    return svc._estacion_repo.create(
        {
            "afiliado_id": afiliado.afiliado_id,
            "plaza_id": plaza.plaza_id,
            "nombre_estacion": nombre,
            "tipo_senal": tipo_senal,
        }
    )


# ── helpers ─────────────────────────────────────────────────────────────────────
def _tarifa(
    svc: TarifaService,
    estacion_id: uuid.UUID,
    *,
    tipo: str = "fm",
    dur: str = "30s",
    producto: str = "spot",
    bruta: str = "9000",
    desc: str = "10",
    notas: str | None = None,
) -> TarifaPlazaRead:
    return svc.create(
        TarifaPlazaCreate(
            estacion_id=estacion_id,
            tipo_senal=TipoSenal(tipo),
            duracion_spot=DuracionSpot(dur),
            producto=ProductoTarifa(producto),
            tarifa_bruta=Decimal(bruta),
            descuento_pct=Decimal(desc),
            notas=notas,
        ),
        USUARIO,
    )


# ── Campo calculado ───────────────────────────────────────────────────────────
def test_tarifa_neta_calculada(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    assert t.tarifa_neta == Decimal("8100.00")


def test_tarifa_neta_redondeo_medio_arriba() -> None:
    # 100 * (1 - 33.335/100) = 66.665 → ROUND_HALF_UP → 66.67
    assert calcular_tarifa_neta(Decimal("100"), Decimal("33.335")) == Decimal("66.67")


def test_tarifa_neta_no_esta_en_los_schemas_de_entrada() -> None:
    # El campo calculado NO se acepta del cliente: no existe en Create/Update.
    assert "tarifa_neta" not in TarifaPlazaCreate.model_fields
    assert "tarifa_neta" not in TarifaPlazaUpdate.model_fields


def test_tarifa_neta_se_recalcula_al_editar(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")  # neta 8100
    upd = svc.update(
        t.tarifa_plaza_id,
        TarifaPlazaUpdate(descuento_pct=Decimal("20"), motivo_cambio="Ajuste de prueba"),
        USUARIO,
    )
    assert upd.tarifa_neta == Decimal("7200.00")


# ── Parámetros sensibles: tarifa_bruta / descuento_pct (ADR-099) ──────────────────
def test_alta_audita_ambos_campos_con_anterior_none(
    contexto: tuple[TarifaService, Estacion], sqlite_session: Session
) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    logs_bruta = _logs(sqlite_session, campo="tarifa_bruta")
    logs_desc = _logs(sqlite_session, campo="descuento_pct")
    assert len(logs_bruta) == 1 and len(logs_desc) == 1
    assert logs_bruta[0].entidad == "TarifaPlaza"
    assert logs_bruta[0].entidad_id == str(t.tarifa_plaza_id)
    assert logs_bruta[0].valor_anterior is None
    assert logs_bruta[0].valor_nuevo == "9000"
    assert logs_bruta[0].usuario == "tester"
    assert logs_desc[0].valor_anterior is None
    assert logs_desc[0].valor_nuevo == "10"


def test_editar_tarifa_bruta_con_motivo_audita(
    contexto: tuple[TarifaService, Estacion], sqlite_session: Session
) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    svc.update(
        t.tarifa_plaza_id,
        TarifaPlazaUpdate(tarifa_bruta=Decimal("9500"), motivo_cambio="Ajuste de temporada"),
        USUARIO,
    )
    logs = _logs(sqlite_session, campo="tarifa_bruta")
    assert len(logs) == 2  # uno del alta + uno de la edición
    edicion = next(log for log in logs if log.valor_anterior is not None)
    assert edicion.valor_anterior == "9000.00"
    assert edicion.valor_nuevo == "9500"
    assert edicion.motivo_cambio == "Ajuste de temporada"


def test_editar_ambos_campos_con_un_solo_motivo_audita_los_dos(
    contexto: tuple[TarifaService, Estacion], sqlite_session: Session
) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    svc.update(
        t.tarifa_plaza_id,
        TarifaPlazaUpdate(
            tarifa_bruta=Decimal("9500"),
            descuento_pct=Decimal("15"),
            motivo_cambio="Renegociación",
        ),
        USUARIO,
    )
    edicion_bruta = next(
        log for log in _logs(sqlite_session, campo="tarifa_bruta") if log.valor_anterior is not None
    )
    edicion_desc = next(
        log
        for log in _logs(sqlite_session, campo="descuento_pct")
        if log.valor_anterior is not None
    )
    assert edicion_bruta.motivo_cambio == "Renegociación"
    assert edicion_desc.motivo_cambio == "Renegociación"


def test_editar_tarifa_bruta_sin_motivo_rechazado(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    with pytest.raises(DomainError):
        svc.update(t.tarifa_plaza_id, TarifaPlazaUpdate(tarifa_bruta=Decimal("9500")), USUARIO)


def test_editar_sensible_no_admin_rechazado(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    with pytest.raises(PermissionDeniedError):
        svc.update(
            t.tarifa_plaza_id,
            TarifaPlazaUpdate(tarifa_bruta=Decimal("9500"), motivo_cambio="intento no autorizado"),
            VENTAS,
        )


def test_editar_mismo_valor_no_audita(
    contexto: tuple[TarifaService, Estacion], sqlite_session: Session
) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    # Mismo valor (9000 == 9000.00): no hay cambio → no exige motivo ni audita.
    svc.update(t.tarifa_plaza_id, TarifaPlazaUpdate(tarifa_bruta=Decimal("9000.00")), USUARIO)
    logs = _logs(sqlite_session, campo="tarifa_bruta")
    assert len(logs) == 1  # solo el del alta


def test_editar_campo_no_sensible_no_audita(
    contexto: tuple[TarifaService, Estacion], sqlite_session: Session
) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id)
    svc.update(t.tarifa_plaza_id, TarifaPlazaUpdate(notas="ajuste"), USUARIO)
    logs = _logs(sqlite_session)
    assert len(logs) == 2  # solo los del alta (tarifa_bruta + descuento_pct)


def test_motivo_cambio_no_es_columna() -> None:
    # `motivo_cambio` es transitorio: se consume en el servicio y no se persiste.
    assert not hasattr(TarifaPlaza, "motivo_cambio")
    assert "motivo_cambio" not in TarifaPlazaCreate.model_fields


def test_historial_registra_alta_y_edicion(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id, bruta="9000", desc="10")
    svc.update(
        t.tarifa_plaza_id,
        TarifaPlazaUpdate(tarifa_bruta=Decimal("9500"), motivo_cambio="Ajuste"),
        USUARIO,
    )
    hist = svc.historial(t.tarifa_plaza_id)
    assert len(hist) == 3  # alta (bruta + descuento) + 1 edición
    assert all(h.entidad == "TarifaPlaza" and h.entidad_id == str(t.tarifa_plaza_id) for h in hist)
    edicion = next(h for h in hist if h.campo == "tarifa_bruta" and h.valor_anterior is not None)
    assert edicion.valor_anterior == "9000.00"
    assert edicion.valor_nuevo == "9500"
    assert edicion.motivo_cambio == "Ajuste"


def test_historial_tarifa_inexistente_404(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, _ = contexto
    with pytest.raises(NotFoundError):
        svc.historial(uuid.uuid4())


# ── Sin vigencia (ADR-097) ─────────────────────────────────────────────────────
def test_tarifa_sin_campos_de_vigencia() -> None:
    # Los campos de vigencia se eliminaron por completo (ADR-097): ni siquiera existen
    # en los schemas de entrada.
    assert "vigencia_desde" not in TarifaPlazaCreate.model_fields
    assert "vigencia_hasta" not in TarifaPlazaCreate.model_fields
    assert "vigencia_desde" not in TarifaPlazaUpdate.model_fields
    assert "vigencia_hasta" not in TarifaPlazaUpdate.model_fields


# ── Sin duplicado activo (ADR-097, reemplaza el solapamiento por vigencia) ────────
def test_duplicado_activo_rechazado(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    _tarifa(svc, estacion.estacion_id, tipo="fm", dur="30s", producto="spot")
    with pytest.raises(ConflictError):
        _tarifa(svc, estacion.estacion_id, tipo="fm", dur="30s", producto="spot")


def test_distinta_combinacion_no_duplica(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    _tarifa(svc, estacion.estacion_id, tipo="fm", dur="30s", producto="spot")
    # Misma estación, pero distinta señal / duración / producto → no hay duplicado.
    t_60 = _tarifa(svc, estacion.estacion_id, tipo="fm", dur="60s", producto="spot")
    t_mencion = _tarifa(svc, estacion.estacion_id, tipo="fm", dur="30s", producto="mencion")
    assert t_60.tarifa_plaza_id and t_mencion.tarifa_plaza_id


def test_duplicado_pero_la_existente_esta_inactiva_ok(
    contexto: tuple[TarifaService, Estacion],
) -> None:
    svc, estacion = contexto
    t1 = _tarifa(svc, estacion.estacion_id)
    svc.cambiar_estado(t1.tarifa_plaza_id, activo=False, usuario=USUARIO)
    # La inactiva no bloquea: se puede crear otra activa con la misma combinación.
    t2 = _tarifa(svc, estacion.estacion_id)
    assert t2.tarifa_plaza_id is not None


def test_update_no_choca_consigo_misma(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id)
    # Editar la misma tarifa (cambia notas, misma combinación) NO debe verse como duplicado.
    upd = svc.update(t.tarifa_plaza_id, TarifaPlazaUpdate(notas="ajuste"), USUARIO)
    assert upd.notas == "ajuste"


def test_reactivar_con_duplicado_rechazado(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    a = _tarifa(svc, estacion.estacion_id)
    svc.cambiar_estado(a.tarifa_plaza_id, activo=False, usuario=USUARIO)
    # Con A inactiva, B toma la misma combinación sin conflicto.
    _tarifa(svc, estacion.estacion_id)
    # Reactivar A ahora chocaría con B.
    with pytest.raises(ConflictError):
        svc.cambiar_estado(a.tarifa_plaza_id, activo=True, usuario=USUARIO)


# ── Dependencia de Estación ─────────────────────────────────────────────────────
def test_estacion_inexistente_rechazada(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, _ = contexto
    with pytest.raises(NotFoundError):
        _tarifa(svc, uuid.uuid4())


# ── ENUMs ─────────────────────────────────────────────────────────────────────
def test_tipo_senal_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            estacion_id=uuid.uuid4(),
            tipo_senal="xx",
            duracion_spot=DuracionSpot.S30,
            producto=ProductoTarifa.SPOT,
            tarifa_bruta=Decimal("100"),
        )


def test_duracion_spot_invalida_rechazada() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            estacion_id=uuid.uuid4(),
            tipo_senal=TipoSenal.FM,
            duracion_spot="45s",
            producto=ProductoTarifa.SPOT,
            tarifa_bruta=Decimal("100"),
        )


def test_producto_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            estacion_id=uuid.uuid4(),
            tipo_senal=TipoSenal.FM,
            duracion_spot=DuracionSpot.S30,
            producto="jingle",
            tarifa_bruta=Decimal("100"),
        )


def test_descuento_fuera_de_rango_rechazado() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            estacion_id=uuid.uuid4(),
            tipo_senal=TipoSenal.FM,
            duracion_spot=DuracionSpot.S30,
            producto=ProductoTarifa.SPOT,
            tarifa_bruta=Decimal("100"),
            descuento_pct=Decimal("120"),
        )


# ── Enriquecimiento + baja lógica + filtros ──────────────────────────────────────
def test_enriquecimiento_estacion(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id)
    leido = svc.get(t.tarifa_plaza_id)
    assert leido.estacion_nombre == "XHRC-FM"


def test_baja_logica(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id)
    baja = svc.cambiar_estado(t.tarifa_plaza_id, activo=False, usuario=USUARIO)
    assert baja.activo is False
    assert svc.list(ListParams(activo=False)).total == 1
    assert svc.list(ListParams(activo=True)).total == 0


def test_created_by_se_guarda(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    t = _tarifa(svc, estacion.estacion_id)
    assert t.created_by == "tester"


# ── Búsqueda `q` (nombre/siglas de estación + notas, vía JOIN) ───────────────────
def test_busqueda_q_por_nombre_de_estacion(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, xhrc = contexto  # "XHRC-FM"
    otra = _crear_estacion(svc, "XEW-Leon")
    _tarifa(svc, xhrc.estacion_id)
    _tarifa(svc, otra.estacion_id)

    res = svc.list(ListParams(q="xew"))  # parcial + case-insensitive
    assert res.total == 1
    assert res.items[0].estacion_id == otra.estacion_id


def test_busqueda_q_por_notas(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    _tarifa(svc, estacion.estacion_id, tipo="fm", notas="Temporada alta")
    _tarifa(svc, estacion.estacion_id, tipo="am", notas=None)
    res = svc.list(ListParams(q="temporada"))
    assert res.total == 1
    assert res.items[0].notas == "Temporada alta"


def test_busqueda_q_sin_coincidencia(contexto: tuple[TarifaService, Estacion]) -> None:
    svc, estacion = contexto
    _tarifa(svc, estacion.estacion_id, notas="general")
    assert svc.list(ListParams(q="zzz-no-existe")).total == 0


def test_busqueda_q_join_compila_para_sqlserver() -> None:
    """La búsqueda `q` hace JOIN a estacion y usa `ilike` (portable: `lower() LIKE lower()`
    en SQL Server), no operadores no portables. Guard a nivel de dialecto (ver ADR-014)."""
    patron = "%xhrc%"
    stmt = (
        select(TarifaPlaza)
        .join(Estacion, TarifaPlaza.estacion_id == Estacion.estacion_id)
        .where(
            or_(
                Estacion.nombre_estacion.ilike(patron),
                Estacion.siglas.ilike(patron),
                TarifaPlaza.notas.ilike(patron),
            )
        )
    )
    sql = str(stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
    assert "JOIN" in sql.upper()
    assert "LIKE" in sql.upper()
    assert "lower(" in sql.lower()  # ilike → lower(col) LIKE lower(patrón)


# ── Portabilidad a SQL Server (regresión ADR-014) ────────────────────────────────
def test_duplicado_filtro_compila_para_sqlserver() -> None:
    """El filtro de duplicado activo usa `activo == True` → debe rendir `activo = 1` en
    SQL Server (nunca `IS 1`, inválido). Fija el criterio a nivel de dialecto (ver
    ADR-014)."""
    stmt = select(TarifaPlaza).where(TarifaPlaza.activo == True)  # noqa: E712
    dialecto = mssql.dialect()  # type: ignore[no-untyped-call]
    sql = str(stmt.compile(dialect=dialecto, compile_kwargs={"literal_binds": True}))
    assert "activo = 1" in sql
    assert "IS 1" not in sql and "IS 0" not in sql
