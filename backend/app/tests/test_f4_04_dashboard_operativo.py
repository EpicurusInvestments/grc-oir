"""Pruebas F4-04 — Dashboard operativo (módulo `reportes`, solo lectura).

Cumplimiento por estación (ordenado vs. ejecutado), incidencias por afiliado (los 5
tipos) y composición de incidencias. Reutiliza los servicios REALES de F1
(`OrdenClienteService`/`OrdenEstacionService`) para producir `Verificacion`/
`Incidencia` tal como lo haría el flujo real (`avanzar_reales`/`cancelar_dia`) — no se
insertan esas dos tablas a mano salvo para los 2 tipos de incidencia que hoy no tienen
ningún flujo automático (`cambio_horario`/`cambio_fecha`, ver docstring de
`incidencia.py`).

Decisiones de esta tanda (ver plan F4, Tanda 3): NO se resta `cantidad_spots_bonificables`
de ordenado/ejecutado; solo cuentan días de `OrdenEstacionDia` con `Verificacion` YA
creada y `cancelada=False`; "Afiliados activos" = afiliados con al menos un día así en
la ventana.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.core.security import Area, CurrentUser
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.cuenta_contable import CuentaContable  # noqa: F401 — registra la tabla
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.incidencia import Incidencia  # noqa: F401 — registra la tabla
from app.modules.ordenes.orden_cliente import (
    OrdenCliente,
    OrdenClienteCreate,
    OrdenClienteRepository,
    OrdenClienteService,
)
from app.modules.ordenes.orden_estacion import (
    OrdenEstacion,
    OrdenEstacionCreate,
    OrdenEstacionDia,
    OrdenEstacionDiaCancelarIn,
    OrdenEstacionDiaCreate,
    OrdenEstacionDiaRealIn,
    OrdenEstacionRealesIn,
    OrdenEstacionRepository,
    OrdenEstacionService,
)
from app.modules.ordenes.verificacion import Verificacion
from app.modules.reportes.repository import ReportesRepository
from app.modules.reportes.router import router as reportes_router
from app.modules.reportes.service import ReportesService
from app.modules.usuarios.models import Usuario

VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")
# Fechas en el futuro respecto a "hoy": `OrdenClienteCreate` rechaza una campaña que
# inicie en el pasado — se elige un mes bien adelante para que la prueba no dependa de
# cuándo se corra.
MES = "2027-03"
D1 = date(2027, 3, 5)
D2 = date(2027, 3, 6)
D3 = date(2027, 3, 7)


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
def cat(db: Session) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    uid = uuid.uuid4()
    db.add(
        Usuario(usuario_id=uid, nombre_usuario="dev.admin", email="dev.admin@x.com", area="admin")
    )

    plaza_id = uuid.uuid4()
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="León"))
    ids["plaza"] = plaza_id

    for clave, nombre_afiliado, nombre_estacion in (
        ("1", "OIR Bajío", "XHLE-FM"),
        ("2", "OIR Golfo", "XHGO-FM"),
    ):
        afiliado_id = uuid.uuid4()
        db.add(
            Afiliado(
                afiliado_id=afiliado_id,
                nombre_afiliado=nombre_afiliado,
                razon_social_afiliado=f"{nombre_afiliado} SA de CV",
                rfc_afiliado=f"AUN90010{clave}AB1",
            )
        )
        ids[f"afiliado_{clave}"] = afiliado_id

        estacion_id = uuid.uuid4()
        db.add(
            Estacion(
                estacion_id=estacion_id,
                afiliado_id=afiliado_id,
                plaza_id=plaza_id,
                nombre_estacion=nombre_estacion,
                frecuencia="97.7 FM",
                tipo_senal="fm",
            )
        )
        ids[f"estacion_{clave}"] = estacion_id

    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id,
            nombre_empresa="Radio Publicidad XHMéxico, S.A. de C.V.",
            rfc_empresa="OTE900101AB1",
            direccion_empresa="Av. Constituyentes 1154, CDMX",
        )
    )
    ids["empresa"] = empresa_id

    vendedor_id = uuid.uuid4()
    db.add(
        Vendedor(
            vendedor_id=vendedor_id,
            nombre_vendedor="Vendedor Uno",
            porcentaje_comision_default=Decimal("4.00"),
        )
    )
    ids["vendedor"] = vendedor_id

    anunciante_id = uuid.uuid4()
    db.add(
        Anunciante(
            anunciante_id=anunciante_id,
            nombre_comercial="Grupo Bimbo",
            nombre_fiscal="Grupo Bimbo SA de CV",
            rfc_anunciante="ANU900101AB1",
            dias_credito_default=30,
        )
    )
    ids["anunciante"] = anunciante_id

    db.commit()
    return ids


@pytest.fixture
def oc_svc(db: Session) -> OrdenClienteService:
    repo = OrdenClienteRepository(db, OrdenCliente, search_columns=[OrdenCliente.folio_orden])
    return OrdenClienteService(repo)


@pytest.fixture
def oe_svc(db: Session) -> OrdenEstacionService:
    repo = OrdenEstacionRepository(
        db, OrdenEstacion, search_columns=[OrdenEstacion.folio_orden_estacion]
    )
    return OrdenEstacionService(repo)


def _oc(
    cat: dict[str, uuid.UUID], oc_svc: OrdenClienteService, *, total_spots: int = 100
) -> uuid.UUID:
    oc = oc_svc.create(
        OrdenClienteCreate(
            numero_orden_cliente=f"PO-{uuid.uuid4().hex[:8]}",
            fecha_venta=D1,
            empresa_facturadora_id=cat["empresa"],
            vendedor_principal_id=cat["vendedor"],
            anunciante_id=cat["anunciante"],
            fecha_inicio_campania=D1 - timedelta(days=5),
            fecha_fin_campania=D3 + timedelta(days=30),
            producto_tarifa="spot",
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=total_spots,
        ),
        VENTAS,
    )
    return oc.orden_id


def _oe(
    cat: dict[str, uuid.UUID],
    oe_svc: OrdenEstacionService,
    orden_id: uuid.UUID,
    *,
    estacion: str = "1",
    dias: list[OrdenEstacionDiaCreate],
    cantidad_spots_bonificables: int = 0,
) -> uuid.UUID:
    oe = oe_svc.create(
        OrdenEstacionCreate(
            orden_id=orden_id,
            estacion_id=cat[f"estacion_{estacion}"],
            producto_tarifa="spot",
            duracion_spot="30s",
            precio_spot=Decimal("800.00"),
            cantidad_spots_bonificables=cantidad_spots_bonificables,
            dias=dias,
        ),
        VENTAS,
    )
    return oe.orden_estacion_id


def _dia(fecha: date, spots: int) -> OrdenEstacionDiaCreate:
    return OrdenEstacionDiaCreate(
        fecha_transmision=fecha, hora_inicio=time(7, 0), hora_fin=time(7, 0), spots_asignados=spots
    )


def _svc(db: Session) -> ReportesService:
    return ReportesService(ReportesRepository(db))


def _dia_ids(db: Session, orden_estacion_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = (
        select(OrdenEstacionDia.orden_estacion_dia_id)
        .where(OrdenEstacionDia.orden_estacion_id == orden_estacion_id)
        .order_by(OrdenEstacionDia.fecha_transmision)
    )
    return list(db.scalars(stmt).all())


def _agrega_incidencia_manual(
    db: Session, verificacion_id: uuid.UUID, orden_estacion_id: uuid.UUID, tipo: str, fecha: date
) -> None:
    """`cambio_horario`/`cambio_fecha` no tienen ningún flujo automático hoy (ver
    docstring de `incidencia.py`) — se insertan directo, reutilizando el `verificacion_id`
    de un día ya verificado (sin UNIQUE en esa FK, puede haber varias incidencias por
    verificación)."""
    db.add(
        Incidencia(
            incidencia_id=uuid.uuid4(),
            verificacion_id=verificacion_id,
            orden_estacion_id=orden_estacion_id,
            tipo_incidencia=tipo,
            spots_ordenados=10,
            spots_ejecutados=10,
            diferencia_spots=0,
            fecha_incidencia=fecha,
        )
    )
    db.commit()


def test_cumplimiento_solo_cuenta_estacion_con_dias_verificados(
    db: Session,
    cat: dict[str, uuid.UUID],
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
) -> None:
    """Estación 1 (verificada) aparece con sus sumas; Estación 2 (nunca avanzada a
    reales) NO aparece — decisión 2: un día sin `Verificacion` no cuenta ni penaliza."""
    oc_id = _oc(cat, oc_svc)
    oe1 = _oe(cat, oe_svc, oc_id, estacion="1", dias=[_dia(D1, 10), _dia(D2, 10)])
    oe_svc.avanzar_reales(
        oe1,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    orden_estacion_dia_id=_dia_ids(db, oe1)[1],
                    spots_verificados=8,
                )
            ]
        ),
        VENTAS,
    )
    _oe(cat, oe_svc, oc_id, estacion="2", dias=[_dia(D1, 5)])  # nunca se avanza

    r = _svc(db).dashboard_operativo("mes", MES)
    por_estacion = {e.nombre_estacion: e for e in r.cumplimiento_por_estacion}
    assert "XHLE-FM" in por_estacion
    assert por_estacion["XHLE-FM"].ordenado == 20
    assert por_estacion["XHLE-FM"].ejecutado == 18  # 10 (exacto) + 8 (faltante)
    assert "XHGO-FM" not in por_estacion
    assert r.spots_ordenados_total == 20
    assert r.spots_transmitidos_total == 18
    assert r.cumplimiento_general_pct == (Decimal("18") / Decimal("20") * 100).quantize(
        Decimal("0.01")
    )


def test_bonificables_no_se_restan_de_ordenado_ni_ejecutado(
    db: Session,
    cat: dict[str, uuid.UUID],
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
) -> None:
    oc_id = _oc(cat, oc_svc)
    oe1 = _oe(cat, oe_svc, oc_id, estacion="1", dias=[_dia(D1, 10)], cantidad_spots_bonificables=3)
    oe_svc.avanzar_reales(oe1, OrdenEstacionRealesIn(dias=[]), VENTAS)  # sin excepciones

    r = _svc(db).dashboard_operativo("mes", MES)
    fila = next(e for e in r.cumplimiento_por_estacion if e.nombre_estacion == "XHLE-FM")
    assert fila.ordenado == 10  # NO se resta cantidad_spots_bonificables (decisión 1)
    assert fila.ejecutado == 10


def test_dia_cancelado_se_excluye_de_cumplimiento_y_genera_spot_no_emitido(
    db: Session,
    cat: dict[str, uuid.UUID],
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
) -> None:
    oc_id = _oc(cat, oc_svc)
    oe1 = _oe(cat, oe_svc, oc_id, estacion="1", dias=[_dia(D1, 10), _dia(D2, 6)])
    dia_cancelado = _dia_ids(db, oe1)[1]
    oe_svc.cancelar_dia(
        oe1, dia_cancelado, OrdenEstacionDiaCancelarIn(motivo="Falla técnica del afiliado"), VENTAS
    )
    oe_svc.avanzar_reales(oe1, OrdenEstacionRealesIn(dias=[]), VENTAS)

    r = _svc(db).dashboard_operativo("mes", MES)
    fila = next(e for e in r.cumplimiento_por_estacion if e.nombre_estacion == "XHLE-FM")
    assert fila.ordenado == 10  # el día cancelado (6 spots) no cuenta
    assert fila.ejecutado == 10
    composicion = {c.tipo_incidencia: c.total for c in r.composicion_incidencias}
    assert composicion["spot_no_emitido"] == 1


def test_composicion_incidencias_incluye_los_5_tipos(
    db: Session,
    cat: dict[str, uuid.UUID],
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
) -> None:
    oc_id = _oc(cat, oc_svc, total_spots=200)
    oe1 = _oe(cat, oe_svc, oc_id, estacion="1", dias=[_dia(D1, 10), _dia(D2, 10), _dia(D3, 5)])
    ids = _dia_ids(db, oe1)
    oe_svc.cancelar_dia(
        oe1, ids[2], OrdenEstacionDiaCancelarIn(motivo="Transmisión cancelada"), VENTAS
    )
    oe_svc.avanzar_reales(
        oe1,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    orden_estacion_dia_id=ids[0], spots_verificados=6
                ),  # faltante
                OrdenEstacionDiaRealIn(
                    orden_estacion_dia_id=ids[1], spots_verificados=12
                ),  # excedente
            ]
        ),
        VENTAS,
    )
    verificacion_id = db.scalar(
        select(Verificacion.verificacion_id).where(Verificacion.orden_estacion_dia_id == ids[0])
    )
    assert verificacion_id is not None
    _agrega_incidencia_manual(db, verificacion_id, oe1, "cambio_horario", D1)
    _agrega_incidencia_manual(db, verificacion_id, oe1, "cambio_fecha", D1)

    r = _svc(db).dashboard_operativo("mes", MES)
    composicion = {c.tipo_incidencia: c.total for c in r.composicion_incidencias}
    assert composicion == {
        "faltante": 1,
        "excedente": 1,
        "cambio_horario": 1,
        "cambio_fecha": 1,
        "spot_no_emitido": 1,
    }
    assert r.incidencias_total == 5
    assert composicion["faltante"] + composicion["excedente"] == sum(
        1 for c in r.composicion_incidencias if c.tipo_incidencia in ("faltante", "excedente")
    )
    assert all(c.pct == Decimal("20.00") for c in r.composicion_incidencias)


def test_incidencias_por_afiliado_desglose_y_tasa_alerta(
    db: Session,
    cat: dict[str, uuid.UUID],
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
) -> None:
    """Afiliado 1: 1 OE verificada en la ventana, con 2 incidencias → tasa 200% (>10%,
    alerta). Afiliado 2: sin ninguna actividad → ni cuenta en "activos" ni aparece."""
    oc_id = _oc(cat, oc_svc, total_spots=200)
    oe1 = _oe(cat, oe_svc, oc_id, estacion="1", dias=[_dia(D1, 10), _dia(D2, 10)])
    ids = _dia_ids(db, oe1)
    oe_svc.avanzar_reales(
        oe1,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    orden_estacion_dia_id=ids[0], spots_verificados=6
                ),  # faltante
                OrdenEstacionDiaRealIn(
                    orden_estacion_dia_id=ids[1], spots_verificados=15
                ),  # excedente
            ]
        ),
        VENTAS,
    )

    r = _svc(db).dashboard_operativo("mes", MES)
    assert r.afiliados_activos == 1
    por_afiliado = {a.nombre_afiliado: a for a in r.incidencias_por_afiliado}
    assert "OIR Golfo" not in por_afiliado
    fila = por_afiliado["OIR Bajío"]
    assert fila.total == 2
    assert fila.faltantes == 1
    assert fila.excedentes == 1
    assert fila.oe_totales == 1
    assert fila.tasa_pct == Decimal("200.00")
    assert fila.alerta is True


def test_ventana_sin_datos_no_truena(db: Session) -> None:
    r = _svc(db).dashboard_operativo("mes", MES)
    assert r.cumplimiento_general_pct is None
    assert r.spots_ordenados_total == 0
    assert r.afiliados_activos == 0
    assert r.cumplimiento_por_estacion == []
    assert r.incidencias_por_afiliado == []
    assert all(c.total == 0 for c in r.composicion_incidencias)


def test_ventana_invalida_lanza_error() -> None:
    from app.core.errors import DomainError

    with pytest.raises(DomainError):
        ReportesService(ReportesRepository(None)).dashboard_operativo(  # type: ignore[arg-type]
            "trimestre_raro", MES
        )


# ── RBAC y exportación del endpoint ─────────────────────────────────────────────
@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.core import config

    monkeypatch.setattr(config.settings, "auth_provider", "dev_headers")
    monkeypatch.setattr(config.settings, "app_env", "development")

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(reportes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def test_rbac_reportes_operativo_todas_las_areas(client: TestClient) -> None:
    """A diferencia de los otros 3 dashboards de F4, `reportes_operativo` es para TODAS
    las áreas (ficha F4) — incluida Nóminas, que no ve ningún otro reporte de F4."""
    ruta = "/api/v1/reportes/operativo"
    for area in (
        "ventas",
        "facturacion",
        "tesoreria",
        "cxc",
        "cxp",
        "direccion",
        "nominas",
        "admin",
    ):
        assert client.get(ruta, headers=_hdr(area)).status_code == 200, area


def test_exportar_operativo_xlsx_y_csv_ok(client: TestClient) -> None:
    for formato in ("xlsx", "csv"):
        r = client.get(
            "/api/v1/reportes/operativo/exportar",
            params={"formato": formato},
            headers=_hdr("direccion"),
        )
        assert r.status_code == 200, r.text
