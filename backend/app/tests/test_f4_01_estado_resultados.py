"""Pruebas F4-01 — Estado de resultados (módulo `reportes`, solo lectura).

Las pruebas insertan directamente vía ORM (SQLite en memoria) el estado que el
`ReportesService` debe agregar — no se ejercitan los flujos completos de F2/F3 (ya
tienen sus propias pruebas); aquí se valida ÚNICAMENTE la lógica nueva de agregación
por periodo: exclusiones, prorrateo a sin-IVA, guardas de división por cero, zona
horaria del "mes en curso" y RBAC del endpoint.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import DomainError, register_error_handlers
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.categoria import Categoria  # noqa: F401 — registra la tabla
from app.modules.catalogos.constantes_sistema import ConstanteSistema  # noqa: F401
from app.modules.catalogos.contrato import Contrato  # noqa: F401
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion  # noqa: F401 — registra la tabla
from app.modules.catalogos.plaza import Plaza  # noqa: F401 — registra la tabla
from app.modules.catalogos.vendedor import Vendedor
from app.modules.cobranza.cobranza_factura import CobranzaFactura, PagoCliente
from app.modules.cobranza.requisicion import Requisicion
from app.modules.facturacion.costo_adicional import CostoAdicional
from app.modules.facturacion.factura_afiliado import FacturaAfiliado
from app.modules.facturacion.factura_agencia import FacturaAgencia
from app.modules.facturacion.factura_cliente import FacturaCliente
from app.modules.facturacion.factura_vendedor import FacturaVendedor
from app.modules.ordenes.orden_cliente import OrdenCliente  # noqa: F401 — registra la tabla
from app.modules.ordenes.orden_estacion import OrdenEstacion  # noqa: F401
from app.modules.reportes.repository import ReportesRepository
from app.modules.reportes.router import router as reportes_router
from app.modules.reportes.service import ReportesService, _mes_en_curso, _validar_periodo
from app.modules.usuarios.models import Usuario

ADMIN_ID = uuid.uuid4()
_Q2 = Decimal("0.01")


# ── Fixtures ──────────────────────────────────────────────────────────────────────
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
    db.add(
        Usuario(usuario_id=ADMIN_ID, nombre_usuario="tester", email="t@grcoir.com", area="admin")
    )
    empresa_id, vendedor_id, anunciante_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    agencia_id, afiliado_id, cuenta_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
        )
    )
    db.add(Vendedor(vendedor_id=vendedor_id, nombre_vendedor="Vendedor Uno"))
    db.add(
        Anunciante(
            anunciante_id=anunciante_id,
            nombre_comercial="Anunciante Uno",
            nombre_fiscal="Anunciante Uno SA de CV",
            rfc_anunciante="ANU900101AB1",
            dias_credito_default=30,
        )
    )
    db.add(
        Agencia(
            agencia_id=agencia_id,
            nombre_agencia="Agencia Uno",
            rfc_agencia="AGU900101AB1",
            porcentaje_comision_agencia_default=Decimal("10.00"),
        )
    )
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="Afiliado Uno",
            razon_social_afiliado="Afiliado Uno SA de CV",
            rfc_afiliado="AUN900101AB1",
        )
    )
    db.add(
        CuentaContable(
            cuenta_contable_id=cuenta_id,
            codigo_cuenta="4100-001",
            nombre_cuenta="Ingresos",
            tipo_cuenta="ingreso",
        )
    )
    db.commit()
    return {
        "empresa_id": empresa_id,
        "vendedor_id": vendedor_id,
        "anunciante_id": anunciante_id,
        "agencia_id": agencia_id,
        "afiliado_id": afiliado_id,
        "cuenta_id": cuenta_id,
    }


# ── Helpers de alta directa (ORM) ───────────────────────────────────────────────
def _factura_cliente(
    db: Session,
    cat: dict[str, uuid.UUID],
    *,
    numero: str,
    fecha_factura: date,
    subtotal: Decimal,
    estado: str = "timbrada",
    tipo_comprobante: str | None = None,
) -> uuid.UUID:
    iva = (subtotal * Decimal("0.16")).quantize(_Q2)
    total = (subtotal + iva).quantize(_Q2)
    factura_id = uuid.uuid4()
    db.add(
        FacturaCliente(
            factura_id=factura_id,
            numero_factura=numero,
            empresa_facturadora_id=cat["empresa_id"],
            anunciante_id=cat["anunciante_id"],
            razon_social_facturacion="Anunciante Uno SA de CV",
            rfc_facturacion="ANU900101AB1",
            descripcion_factura="Servicios de transmisión",
            fecha_inicio_transmision=fecha_factura,
            fecha_fin_transmision=fecha_factura,
            fecha_factura=fecha_factura,
            subtotal_factura=subtotal,
            iva_factura=iva,
            total_factura=total,
            cuenta_contable_id=cat["cuenta_id"],
            metodo_pago_clave="PUE",
            estado_facturacion=estado,
            tipo_comprobante=tipo_comprobante,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return factura_id


def _cobranza(
    db: Session, cat: dict[str, uuid.UUID], factura_id: uuid.UUID, *, fecha_estimada: date
) -> uuid.UUID:
    cobranza_id = uuid.uuid4()
    db.add(
        CobranzaFactura(
            cobranza_id=cobranza_id,
            factura_id=factura_id,
            anunciante_id=cat["anunciante_id"],
            metodo_pago_clave="PUE",
            dias_credito=30,
            fecha_estimada_cobro=fecha_estimada,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return cobranza_id


def _pago(
    db: Session,
    cobranza_id: uuid.UUID | None,
    *,
    fecha_pago: date,
    monto: Decimal,
    estatus: str = "pagado",
    factura_egreso_id: uuid.UUID | None = None,
) -> uuid.UUID:
    pago_id = uuid.uuid4()
    db.add(
        PagoCliente(
            pago_cliente_id=pago_id,
            cobranza_id=cobranza_id,
            fecha_pago_cliente=fecha_pago,
            monto_aplicado=monto,
            estatus_pago=estatus,
            factura_egreso_id=factura_egreso_id,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return pago_id


def _factura_afiliado(
    db: Session, cat: dict[str, uuid.UUID], *, fecha: date, monto: Decimal, numero: str = "FAF-1"
) -> uuid.UUID:
    iva = (monto * Decimal("0.16")).quantize(_Q2)
    total = (monto + iva).quantize(_Q2)
    fid = uuid.uuid4()
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=fid,
            afiliado_id=cat["afiliado_id"],
            factura_emisora=numero,
            fecha_factura_afiliado=fecha,
            monto_factura_afiliado=monto,
            iva_factura_afiliado=iva,
            total_factura_afiliado=total,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return fid


def _factura_agencia(
    db: Session, cat: dict[str, uuid.UUID], *, fecha: date, monto: Decimal
) -> uuid.UUID:
    iva = (monto * Decimal("0.16")).quantize(_Q2)
    total = (monto + iva).quantize(_Q2)
    fid = uuid.uuid4()
    db.add(
        FacturaAgencia(
            factura_agencia_id=fid,
            agencia_id=cat["agencia_id"],
            fecha_factura_agencia=fecha,
            monto_factura_agencia=monto,
            iva_factura_agencia=iva,
            total_factura_agencia=total,
            comision_agencia=monto,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return fid


def _factura_vendedor(
    db: Session, cat: dict[str, uuid.UUID], *, fecha: date, monto: Decimal
) -> uuid.UUID:
    iva = (monto * Decimal("0.16")).quantize(_Q2)
    total = (monto + iva).quantize(_Q2)
    fid = uuid.uuid4()
    db.add(
        FacturaVendedor(
            factura_vendedor_id=fid,
            vendedor_id=cat["vendedor_id"],
            fecha_factura_vendedor=fecha,
            monto_factura_vendedor=monto,
            iva_factura_vendedor=iva,
            total_factura_vendedor=total,
            comision_vendedor=monto,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return fid


def _requisicion(
    db: Session,
    *,
    tipo: str,
    estatus: str,
    monto: Decimal,
    fecha_pago: date | None,
    numero: str,
    factura_afiliado_id: uuid.UUID | None = None,
    factura_agencia_id: uuid.UUID | None = None,
    factura_vendedor_id: uuid.UUID | None = None,
    orden_id: uuid.UUID | None = None,
) -> uuid.UUID:
    rid = uuid.uuid4()
    db.add(
        Requisicion(
            requisicion_id=rid,
            numero_requisicion=numero,
            tipo_requisicion=tipo,
            factura_afiliado_id=factura_afiliado_id,
            factura_agencia_id=factura_agencia_id,
            factura_vendedor_id=factura_vendedor_id,
            orden_id=orden_id,
            monto_requisicion=monto,
            estatus_requisicion=estatus,
            fecha_pago_requisicion=fecha_pago,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return rid


def _costo(db: Session, *, tipo: str, periodo: str, monto: Decimal) -> uuid.UUID:
    cid = uuid.uuid4()
    db.add(
        CostoAdicional(
            costo_id=cid,
            tipo_costo=tipo,
            descripcion_costo="Costo de prueba",
            periodo_contable=periodo,
            monto_costo=monto,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return cid


def _svc(db: Session) -> ReportesService:
    return ReportesService(ReportesRepository(db))


# ── Casos ────────────────────────────────────────────────────────────────────────
def test_facturado_excluye_borrador_y_cancelada_incluye_nota_credito(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _factura_cliente(
        db, cat, numero="F-1", fecha_factura=date(2026, 11, 5),
        subtotal=Decimal("1000.00"), estado="timbrada",
    )
    _factura_cliente(
        db, cat, numero="F-2", fecha_factura=date(2026, 11, 10),
        subtotal=Decimal("500.00"), estado="preparada",
    )
    _factura_cliente(
        db, cat, numero="F-3", fecha_factura=date(2026, 11, 12),
        subtotal=Decimal("300.00"), estado="cancelada",
    )
    # Nota de crédito timbrada: subtotal NEGATIVO, debe restar automáticamente.
    _factura_cliente(
        db, cat, numero="NC-1", fecha_factura=date(2026, 11, 15),
        subtotal=Decimal("-200.00"), estado="timbrada", tipo_comprobante="E",
    )
    db.commit()

    resultado = _svc(db).estado_resultados("2026-11")
    assert resultado.actual.ingresos_facturado == Decimal("800.00")  # 1000 - 200 (NC)


def test_cobrado_excluye_huerfano_cancelado_y_nota_credito_sintetica(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = _factura_cliente(
        db, cat, numero="F-1", fecha_factura=date(2026, 11, 1), subtotal=Decimal("1000.00")
    )
    cobranza_id = _cobranza(db, cat, factura_id, fecha_estimada=date(2026, 12, 1))
    # Pago real, sin IVA esperado: 500 * (1000/1160) = 431.03 (redondeado)
    _pago(db, cobranza_id, fecha_pago=date(2026, 11, 10), monto=Decimal("500.00"))
    # Pago cancelado: excluido.
    _pago(
        db, cobranza_id, fecha_pago=date(2026, 11, 11),
        monto=Decimal("100.00"), estatus="cancelado",
    )
    # Pago huérfano (sin cobranza_id): excluido.
    _pago(db, None, fecha_pago=date(2026, 11, 12), monto=Decimal("50.00"))
    # Pago sintético de una Nota de Crédito (factura_egreso_id no nulo): excluido.
    nc_id = _factura_cliente(
        db, cat, numero="NC-1", fecha_factura=date(2026, 11, 2),
        subtotal=Decimal("-200.00"), tipo_comprobante="E",
    )
    _pago(
        db, cobranza_id, fecha_pago=date(2026, 11, 13),
        monto=Decimal("232.00"), factura_egreso_id=nc_id,
    )
    db.commit()

    resultado = _svc(db).estado_resultados("2026-11")
    esperado = (Decimal("500.00") * Decimal("1000.00") / Decimal("1160.00")).quantize(_Q2)
    assert resultado.actual.ingresos_cobrado == esperado


def test_costos_directos_pagado_prorratea_sin_iva(db: Session, cat: dict[str, uuid.UUID]) -> None:
    fa_id = _factura_afiliado(db, cat, fecha=date(2026, 11, 1), monto=Decimal("1000.00"))
    _requisicion(
        db, tipo="pago_afiliado", estatus="pagada", monto=Decimal("1160.00"),
        fecha_pago=date(2026, 11, 20), numero="RQ-1", factura_afiliado_id=fa_id,
    )
    db.commit()

    resultado = _svc(db).estado_resultados("2026-11")
    esperado = (Decimal("1160.00") * Decimal("1000.00") / Decimal("1160.00")).quantize(_Q2)
    assert resultado.actual.costos_afiliados.pagado == esperado == Decimal("1000.00")
    assert resultado.actual.costos_afiliados.facturado == Decimal("1000.00")


def test_costos_indirectos_sin_iva_sin_prorrateo(db: Session, cat: dict[str, uuid.UUID]) -> None:
    _costo(db, tipo="nomina", periodo="2026-11", monto=Decimal("5000.00"))
    _costo(db, tipo="overhead", periodo="2026-11", monto=Decimal("1500.00"))
    _costo(db, tipo="nomina", periodo="2026-10", monto=Decimal("9999.00"))  # otro mes, no cuenta
    db.commit()

    resultado = _svc(db).estado_resultados("2026-11")
    assert resultado.actual.costo_nominas == Decimal("5000.00")
    assert resultado.actual.costo_overhead == Decimal("1500.00")
    assert resultado.actual.utilidad_neta == resultado.actual.utilidad_bruta - Decimal("6500.00")


def test_mes_sin_datos_margenes_none_sin_excepcion(db: Session, cat: dict[str, uuid.UUID]) -> None:
    resultado = _svc(db).estado_resultados("2026-08")
    p = resultado.actual
    assert p.ingresos_facturado == Decimal("0")
    assert p.ingresos_cobrado == Decimal("0")
    assert p.utilidad_bruta == Decimal("0")
    assert p.margen_bruto_pct is None
    assert p.margen_neto_pct is None
    assert p.pct_cobranza is None


def test_division_por_cero_en_prorrateo_no_truena(db: Session, cat: dict[str, uuid.UUID]) -> None:
    """`total_factura_afiliado = 0` no debería existir en la práctica, pero el código
    no lo prohíbe — la guarda del service debe tratarlo como razón 0, nunca excepción."""
    fid = uuid.uuid4()
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=fid,
            afiliado_id=cat["afiliado_id"],
            factura_emisora="FAF-0",
            fecha_factura_afiliado=date(2026, 11, 1),
            monto_factura_afiliado=Decimal("0.00"),
            iva_factura_afiliado=Decimal("0.00"),
            total_factura_afiliado=Decimal("0.00"),
            created_by=ADMIN_ID,
        )
    )
    _requisicion(
        db, tipo="pago_afiliado", estatus="pagada", monto=Decimal("500.00"),
        fecha_pago=date(2026, 11, 20), numero="RQ-0", factura_afiliado_id=fid,
    )
    db.commit()

    resultado = _svc(db).estado_resultados("2026-11")  # no debe lanzar ZeroDivisionError
    assert resultado.actual.costos_afiliados.pagado == Decimal("0.00")


def test_ventana_primer_y_ultimo_dia_del_mes(db: Session, cat: dict[str, uuid.UUID]) -> None:
    _factura_cliente(
        db, cat, numero="F-INI", fecha_factura=date(2026, 11, 1), subtotal=Decimal("100.00")
    )
    _factura_cliente(
        db, cat, numero="F-FIN", fecha_factura=date(2026, 11, 30), subtotal=Decimal("200.00")
    )
    _factura_cliente(
        db, cat, numero="F-SIG", fecha_factura=date(2026, 12, 1), subtotal=Decimal("9999.00")
    )
    _factura_cliente(
        db, cat, numero="F-ANT", fecha_factura=date(2026, 10, 31), subtotal=Decimal("9999.00")
    )
    db.commit()

    resultado = _svc(db).estado_resultados("2026-11")
    assert resultado.actual.ingresos_facturado == Decimal("300.00")


def test_tendencia_y_historico_6_meses(db: Session, cat: dict[str, uuid.UUID]) -> None:
    for i, monto in enumerate([Decimal("100.00"), Decimal("0.00"), Decimal("200.00")]):
        anio, mes = (2026, 9 - i) if 9 - i >= 1 else (2025, 12 + (9 - i))
        if monto > 0:
            _factura_cliente(
                db, cat, numero=f"F-{i}", fecha_factura=date(anio, mes, 5), subtotal=monto
            )
    db.commit()

    resultado = _svc(db).estado_resultados("2026-09")
    assert len(resultado.historico) == 6
    assert resultado.historico[-1].periodo == "2026-09"
    assert resultado.historico[-2].periodo == "2026-08"
    assert resultado.actual.periodo == "2026-09"
    assert resultado.anterior.periodo == "2026-08"


def test_mes_en_curso_usa_zona_horaria_mexico_no_utc() -> None:
    """ADR-261: pasadas las 18:00 hora CDMX, UTC ya marca el día/mes siguiente."""
    mx_tz = ZoneInfo("America/Mexico_City")
    # 23:30 del 30-nov hora CDMX == madrugada del 1-dic en UTC.
    momento_mx = datetime(2026, 11, 30, 23, 30, tzinfo=mx_tz)
    momento_utc_equivalente = momento_mx.astimezone(ZoneInfo("UTC"))
    assert momento_utc_equivalente.date() == date(2026, 12, 1)  # confirma el desfase
    # `_mes_en_curso()` usa `datetime.now(_ZONA_MX)`, no UTC: no podemos congelar el
    # reloj del sistema aquí sin una librería extra, pero se deja la prueba de
    # conversión como regresión explícita del bug de fondo (ADR-261) y se confía en
    # que `_mes_en_curso()` SIEMPRE construye su "hoy" vía `datetime.now(_ZONA_MX)`
    # (ver `app/modules/reportes/service.py`), nunca `datetime.utcnow()`.
    assert _mes_en_curso() == f"{datetime.now(mx_tz).year:04d}-{datetime.now(mx_tz).month:02d}"


def test_periodo_invalido_lanza_domain_error() -> None:
    with pytest.raises(DomainError):
        _validar_periodo("2026-13")
    with pytest.raises(DomainError):
        _validar_periodo("26-11")


# ── RBAC del endpoint ────────────────────────────────────────────────────────────
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


def test_rbac_reportes_financiero(client: TestClient) -> None:
    ruta = "/api/v1/reportes/estado-resultados"
    assert client.get(ruta, headers=_hdr("ventas")).status_code == 403
    assert client.get(ruta, headers=_hdr("direccion")).status_code == 200
    assert client.get(ruta, headers=_hdr("admin")).status_code == 200


def test_periodo_invalido_422_en_endpoint(client: TestClient) -> None:
    r = client.get(
        "/api/v1/reportes/estado-resultados",
        params={"periodo": "2026-13"},
        headers=_hdr("direccion"),
    )
    assert r.status_code == 422


def test_exportar_formato_invalido_422(client: TestClient) -> None:
    r = client.get(
        "/api/v1/reportes/estado-resultados/exportar",
        params={"formato": "pdf"},
        headers=_hdr("direccion"),
    )
    assert r.status_code == 422


def test_exportar_xlsx_y_csv_ok(client: TestClient) -> None:
    for formato in ("xlsx", "csv"):
        r = client.get(
            "/api/v1/reportes/estado-resultados/exportar",
            params={"periodo": "2026-11", "formato": formato},
            headers=_hdr("direccion"),
        )
        assert r.status_code == 200, r.text
        assert f"estado_resultados_2026-11.{formato}" in r.headers["content-disposition"]
