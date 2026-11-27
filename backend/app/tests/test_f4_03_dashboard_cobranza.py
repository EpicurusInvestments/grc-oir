"""Pruebas F4-03 — Dashboard de cobranza (módulo `reportes`, solo lectura).

"Al corte" de hoy: valida la agregación de aging (una sola consulta, nunca fila por
fila como `CobranzaFacturaService.adeudo_vencido`/ADR-277), el DSO, la exclusión de
`cobrada`, y que "Cobrado del mes" excluya huérfanos/cancelados/el pago sintético de
una Nota de Crédito — mismas reglas que F4-01, aquí CON IVA.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.cobranza.cobranza_factura import CobranzaFactura, PagoCliente
from app.modules.facturacion.factura_cliente import FacturaCliente
from app.modules.ordenes.orden_estacion import OrdenEstacion  # noqa: F401 — registra la tabla
from app.modules.reportes.repository import ReportesRepository
from app.modules.reportes.router import router as reportes_router
from app.modules.reportes.service import _ZONA_MX, ReportesService
from app.modules.usuarios.models import Usuario

ADMIN_ID = uuid.uuid4()
_Q2 = Decimal("0.01")


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
    empresa_id, anunciante_id, anunciante_2_id, cuenta_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
        )
    )
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
        Anunciante(
            anunciante_id=anunciante_2_id,
            nombre_comercial="Anunciante Dos",
            nombre_fiscal="Anunciante Dos SA de CV",
            rfc_anunciante="AND900101AB1",
            dias_credito_default=30,
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
        "anunciante_id": anunciante_id,
        "anunciante_2_id": anunciante_2_id,
        "cuenta_id": cuenta_id,
    }


def _factura_y_cobranza(
    db: Session,
    cat: dict[str, uuid.UUID],
    *,
    numero: str,
    fecha_factura: date,
    total: Decimal,
    fecha_estimada_cobro: date,
    anunciante: str = "anunciante_id",
    estado: str = "timbrada",
    estatus_cobro: str = "pendiente",
    tipo_comprobante: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    subtotal = (total / Decimal("1.16")).quantize(_Q2)
    iva = (total - subtotal).quantize(_Q2)
    factura_id = uuid.uuid4()
    db.add(
        FacturaCliente(
            factura_id=factura_id,
            numero_factura=numero,
            empresa_facturadora_id=cat["empresa_id"],
            anunciante_id=cat[anunciante],
            razon_social_facturacion="Anunciante SA de CV",
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
    cobranza_id = uuid.uuid4()
    db.add(
        CobranzaFactura(
            cobranza_id=cobranza_id,
            factura_id=factura_id,
            anunciante_id=cat[anunciante],
            metodo_pago_clave="PUE",
            dias_credito=30,
            fecha_estimada_cobro=fecha_estimada_cobro,
            estatus_cobro=estatus_cobro,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return factura_id, cobranza_id


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


def _svc(db: Session) -> ReportesService:
    return ReportesService(ReportesRepository(db))


def _hoy() -> date:
    return datetime.now(_ZONA_MX).date()


def test_aging_clasifica_por_dias_vencidos(db: Session, cat: dict[str, uuid.UUID]) -> None:
    hoy = _hoy()
    _factura_y_cobranza(
        db, cat, numero="F-CORRIENTE", fecha_factura=hoy, total=Decimal("1000.00"),
        fecha_estimada_cobro=hoy + timedelta(days=5),
    )
    _factura_y_cobranza(
        db, cat, numero="F-15D", fecha_factura=hoy, total=Decimal("2000.00"),
        fecha_estimada_cobro=hoy - timedelta(days=15),
    )
    _factura_y_cobranza(
        db, cat, numero="F-95D", fecha_factura=hoy, total=Decimal("3000.00"),
        fecha_estimada_cobro=hoy - timedelta(days=95),
    )
    db.commit()

    r = _svc(db).dashboard_cobranza(None, 90)
    por_cubeta = {a.bucket: a for a in r.aging}
    assert por_cubeta["corriente"].importe == Decimal("1000.00")
    assert por_cubeta["1-30"].importe == Decimal("2000.00")
    assert por_cubeta["90+"].importe == Decimal("3000.00")
    assert r.total_por_cobrar == Decimal("6000.00")
    assert r.total_vencido == Decimal("5000.00")  # excluye la corriente
    assert r.total_facturas == 3


def test_cobrada_se_excluye_del_aging(db: Session, cat: dict[str, uuid.UUID]) -> None:
    hoy = _hoy()
    _factura_y_cobranza(
        db, cat, numero="F-1", fecha_factura=hoy, total=Decimal("1000.00"),
        fecha_estimada_cobro=hoy, estatus_cobro="cobrada",
    )
    db.commit()

    r = _svc(db).dashboard_cobranza(None, 90)
    assert r.total_por_cobrar == Decimal("0")
    assert r.total_facturas == 0


def test_saldo_descuenta_pagos_parciales_pagados(db: Session, cat: dict[str, uuid.UUID]) -> None:
    hoy = _hoy()
    _, cobranza_id = _factura_y_cobranza(
        db, cat, numero="F-1", fecha_factura=hoy, total=Decimal("1000.00"),
        fecha_estimada_cobro=hoy, estatus_cobro="cobro_parcial",
    )
    _pago(db, cobranza_id, fecha_pago=hoy, monto=Decimal("400.00"))
    _pago(db, cobranza_id, fecha_pago=hoy, monto=Decimal("100.00"), estatus="cancelado")
    db.commit()

    r = _svc(db).dashboard_cobranza(None, 90)
    assert r.total_por_cobrar == Decimal("600.00")  # 1000 - 400 (el cancelado no cuenta)


def test_dso_global(db: Session, cat: dict[str, uuid.UUID]) -> None:
    hoy = _hoy()
    _factura_y_cobranza(
        db, cat, numero="F-1", fecha_factura=hoy - timedelta(days=10), total=Decimal("900.00"),
        fecha_estimada_cobro=hoy,
    )
    db.commit()

    r = _svc(db).dashboard_cobranza(None, 90)
    # DSO = saldo_por_cobrar / ventas_facturadas_en_ventana * dias_ventana
    assert r.dso_promedio == (Decimal("900.00") / Decimal("900.00") * 90).quantize(_Q2)


def test_cobrado_mes_incluye_huerfano_excluye_cancelado_y_nota_credito(
    db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """"Cobrado del mes" es efectivo real recibido (a diferencia del "Cobrado" del P&L,
    que SÍ excluye huérfanos porque necesita una factura de la que derivar el sin-IVA):
    un pago huérfano (sin asignar todavía a ninguna factura) sigue siendo dinero real
    en el banco, así que SÍ cuenta aquí. `cancelado` y el pago sintético de una Nota de
    Crédito (ADR-293, no es efectivo real) SÍ se excluyen."""
    _, cobranza_id = _factura_y_cobranza(
        db, cat, numero="F-1", fecha_factura=date(2026, 11, 1), total=Decimal("1000.00"),
        fecha_estimada_cobro=date(2026, 12, 1),
    )
    _pago(db, cobranza_id, fecha_pago=date(2026, 11, 10), monto=Decimal("500.00"))
    _pago(
        db, cobranza_id, fecha_pago=date(2026, 11, 11),
        monto=Decimal("50.00"), estatus="cancelado",
    )
    _pago(db, None, fecha_pago=date(2026, 11, 12), monto=Decimal("25.00"))
    nc_id, _ = _factura_y_cobranza(
        db, cat, numero="NC-1", fecha_factura=date(2026, 11, 2), total=Decimal("-200.00"),
        fecha_estimada_cobro=date(2026, 12, 2), tipo_comprobante="E",
    )
    _pago(
        db, cobranza_id, fecha_pago=date(2026, 11, 13), monto=Decimal("200.00"),
        factura_egreso_id=nc_id,
    )
    db.commit()

    r = _svc(db).dashboard_cobranza("2026-11", 90)
    assert r.cobrado_mes == Decimal("525.00")  # 500 (asignado) + 25 (huérfano, SÍ cuenta)


def test_mes_invalido_lanza_error() -> None:
    from app.core.errors import DomainError

    with pytest.raises(DomainError):
        ReportesService(ReportesRepository(None)).dashboard_cobranza("2026-13", 90)  # type: ignore[arg-type]


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


def test_rbac_reportes_cobranza(client: TestClient) -> None:
    ruta = "/api/v1/reportes/cobranza"
    assert client.get(ruta, headers=_hdr("ventas")).status_code == 403
    assert client.get(ruta, headers=_hdr("facturacion")).status_code == 200
    assert client.get(ruta, headers=_hdr("tesoreria")).status_code == 200
    assert client.get(ruta, headers=_hdr("direccion")).status_code == 200
    assert client.get(ruta, headers=_hdr("admin")).status_code == 200


def test_exportar_cobranza_xlsx_y_csv_ok(client: TestClient) -> None:
    for formato in ("xlsx", "csv"):
        r = client.get(
            "/api/v1/reportes/cobranza/exportar",
            params={"formato": formato},
            headers=_hdr("direccion"),
        )
        assert r.status_code == 200, r.text
