"""Pruebas F3 · Requisicion + MovimientoBancario (SQLite).

`Requisicion`: máquina de estados con canal dedicado de autorización (Dirección/Admin,
ADR-046), comisiones sugeridas del catálogo, `diferencia_afiliada` negativa permitida.

`MovimientoBancario`: primera vez que Tesorería captura en el proyecto (canal dedicado,
mismo patrón que la autorización de Dirección), sin matching automático, y el rechazo de
duplicados.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.categoria import Categoria  # noqa: F401 — registra la tabla
from app.modules.catalogos.constantes_sistema import ConstanteSistema  # noqa: F401
from app.modules.catalogos.contrato import Contrato  # noqa: F401 — ídem
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.cobranza.router import router as cobranza_router
from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor, FacturaAfiliado
from app.modules.facturacion.factura_agencia import FacturaAgencia  # noqa: F401
from app.modules.facturacion.factura_cliente import FacturaCliente  # noqa: F401
from app.modules.ordenes.orden_cliente import OrdenCliente
from app.modules.ordenes.orden_estacion import OrdenEstacion  # noqa: F401 — registra la tabla
from app.modules.usuarios.models import Usuario

ADMIN_ID = uuid.uuid4()


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


def _catalogos(db: Session) -> dict[str, uuid.UUID]:
    db.add(
        Usuario(
            usuario_id=ADMIN_ID, nombre_usuario="tester", email="admin@grcoir.com", area="admin"
        )
    )
    plaza_id, afiliado_id, estacion_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="CDMX"))
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="Afiliado Uno",
            razon_social_afiliado="Afiliado Uno SA de CV",
            rfc_afiliado="AUN900101AB1",
        )
    )
    db.add(
        Estacion(
            estacion_id=estacion_id,
            afiliado_id=afiliado_id,
            plaza_id=plaza_id,
            nombre_estacion="XHTEST-FM",
            tipo_senal="fm",
        )
    )
    empresa_id, vendedor_id, anunciante_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
        )
    )
    db.add(
        Vendedor(
            vendedor_id=vendedor_id,
            nombre_vendedor="Vendedor Uno",
            porcentaje_comision_default=Decimal("4.00"),
        )
    )
    db.add(
        Anunciante(
            anunciante_id=anunciante_id,
            nombre_comercial="Anunciante Uno",
            nombre_fiscal="Anunciante Uno SA de CV",
            rfc_anunciante="ANU900101AB1",
        )
    )
    agencia_id, cuenta_id = uuid.uuid4(), uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=agencia_id,
            nombre_agencia="Agencia Uno",
            rfc_agencia="AGU900101AB1",
            porcentaje_comision_agencia_default=Decimal("15.00"),
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
    db.flush()
    return {
        "plaza_id": plaza_id,
        "afiliado_id": afiliado_id,
        "estacion_id": estacion_id,
        "empresa_id": empresa_id,
        "vendedor_id": vendedor_id,
        "anunciante_id": anunciante_id,
        "agencia_id": agencia_id,
        "cuenta_id": cuenta_id,
    }


def _orden(db: Session, cat: dict[str, uuid.UUID], folio: str, total: Decimal) -> uuid.UUID:
    orden_id = uuid.uuid4()
    subtotal = (total / Decimal("1.16")).quantize(Decimal("0.01"))
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden=folio,
            numero_orden_cliente="NUM-" + folio,
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=cat["empresa_id"],
            vendedor_principal_id=cat["vendedor_id"],
            anunciante_id=cat["anunciante_id"],
            agencia_id=cat["agencia_id"],
            fecha_inicio_campania=date(2026, 2, 1),
            fecha_fin_campania=date(2026, 2, 28),
            total_dias_campania=28,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=subtotal,
            iva=(total - subtotal).quantize(Decimal("0.01")),
            total=total,
            estatus_orden="orden_cerrada",
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return orden_id


def _factura_afiliado(db: Session, cat: dict[str, uuid.UUID], total: Decimal) -> uuid.UUID:
    factura_id = uuid.uuid4()
    monto = (total / Decimal("1.16")).quantize(Decimal("0.01"))
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=factura_id,
            afiliado_id=cat["afiliado_id"],
            factura_emisora="AF-001",
            fecha_factura_afiliado=date(2026, 3, 1),
            monto_factura_afiliado=monto,
            iva_factura_afiliado=(total - monto).quantize(Decimal("0.01")),
            total_factura_afiliado=total,
            estatus_factura_afiliado=EstatusFacturaProveedor.AUTORIZADA.value,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return factura_id


@pytest.fixture
def cat(db: Session) -> dict[str, uuid.UUID]:
    datos = _catalogos(db)
    db.commit()
    return datos


@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(cobranza_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


# ══════════════════════════════════════════════════════════════════════════════
# Requisicion — alta con comisiones sugeridas / diferencia negativa
# ══════════════════════════════════════════════════════════════════════════════
def test_alta_comision_vendedor_sugiere_el_porcentaje_del_catalogo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-CV1", Decimal("100000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": "REQ-0001",
            "tipo_requisicion": "comision_vendedor",
            "orden_id": str(orden_id),
            "vendedor_comision_id": str(cat["vendedor_id"]),
            "monto_requisicion": "4000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["porcentaje_comision_vendedor"] == "4.00"  # sugerido de Vendedor
    assert Decimal(body["requisicion_comision_vendedor"]) == Decimal("4000.00")
    assert body["estatus_requisicion"] == "pendiente"


def test_alta_comision_vendedor_rechaza_sin_orden_ni_vendedor(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": "REQ-0002",
            "tipo_requisicion": "comision_vendedor",
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400


def test_alta_pago_afiliado_calcula_diferencia_afiliada_negativa(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """`diferencia_afiliada` puede ser negativa: se pagó MENOS de lo que facturó el
    afiliado (monitoreo de márgenes, sin CHECK >= 0)."""
    factura_af_id = _factura_afiliado(db, cat, Decimal("50000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": "REQ-0003",
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_af_id),
            "monto_requisicion": "45000.00",  # menos que los 50000.00 facturados
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["razon_social_afiliada"] == "Afiliado Uno SA de CV"  # heredado
    assert Decimal(body["diferencia_afiliada"]) == Decimal("-5000.00")


def test_alta_pago_afiliado_requiere_afiliado_id(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": "REQ-0004",
            "tipo_requisicion": "pago_afiliado",
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# Requisicion — máquina de estados + canal dedicado de autorización (ADR-046)
# ══════════════════════════════════════════════════════════════════════════════
def _crear_requisicion_simple(client: TestClient, cat: dict[str, uuid.UUID], numero: str) -> str:
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": numero,
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    return r.json()["requisicion_id"]


def test_cxp_no_puede_autorizar_por_el_canal_operativo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, cat, "REQ-0100")
    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "autorizada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 403


def test_direccion_autoriza_por_el_canal_dedicado(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, cat, "REQ-0101")
    r_cxp = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("cxp")
    )
    assert r_cxp.status_code == 403

    r = client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))
    assert r.status_code == 200, r.text
    assert r.json()["estatus_requisicion"] == "autorizada"


def test_ciclo_completo_pendiente_autorizada_pagada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, cat, "REQ-0102")
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada", "fecha_pago_requisicion": "2026-04-01"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estatus_requisicion"] == "pagada"
    assert body["fecha_pago_requisicion"] == "2026-04-01"


def test_no_se_puede_pagar_una_requisicion_sin_autorizar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, cat, "REQ-0103")
    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 409  # transición inválida: pendiente -> pagada no existe


def test_cancelar_desde_pendiente_y_desde_autorizada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req1 = _crear_requisicion_simple(client, cat, "REQ-0104")
    r1 = client.post(
        f"/api/v1/cobranza/requisiciones/{req1}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    assert r1.status_code == 200
    assert r1.json()["estatus_requisicion"] == "cancelada"

    req2 = _crear_requisicion_simple(client, cat, "REQ-0105")
    client.post(f"/api/v1/cobranza/requisiciones/{req2}/autorizar", headers=_hdr("direccion"))
    r2 = client.post(
        f"/api/v1/cobranza/requisiciones/{req2}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    assert r2.status_code == 200
    assert r2.json()["estatus_requisicion"] == "cancelada"


def test_rbac_direccion_solo_lee_no_puede_capturar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": "REQ-0106",
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("direccion"),
    )
    assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# MovimientoBancario — canal dedicado de Tesorería + duplicados + conciliar manual
# ══════════════════════════════════════════════════════════════════════════════
def test_solo_tesoreria_puede_capturar_un_movimiento(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    payload = {
        "fecha_movimiento": "2026-03-05",
        "tipo_movimiento": "abono",
        "monto_movimiento": "1000.00",
        "referencia_bancaria": "SPEI-001",
    }
    r_cxp = client.post("/api/v1/cobranza/movimientos-bancarios", json=payload, headers=_hdr("cxp"))
    assert r_cxp.status_code == 403

    r_tes = client.post(
        "/api/v1/cobranza/movimientos-bancarios", json=payload, headers=_hdr("tesoreria")
    )
    assert r_tes.status_code == 201, r_tes.text
    assert r_tes.json()["conciliado"] is False


def test_rechaza_movimiento_duplicado(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    payload = {
        "fecha_movimiento": "2026-03-05",
        "tipo_movimiento": "abono",
        "monto_movimiento": "1000.00",
        "referencia_bancaria": "SPEI-002",
    }
    ruta = "/api/v1/cobranza/movimientos-bancarios"
    r1 = client.post(ruta, json=payload, headers=_hdr("tesoreria"))
    assert r1.status_code == 201

    r2 = client.post(ruta, json=payload, headers=_hdr("tesoreria"))
    assert r2.status_code == 409
    assert r2.json()["error"]["codigo"] == "conflicto"


def test_conciliar_es_manual_y_de_una_sola_via(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/cobranza/movimientos-bancarios",
        json={
            "fecha_movimiento": "2026-03-06",
            "tipo_movimiento": "cargo",
            "monto_movimiento": "500.00",
            "referencia_bancaria": "TRANS-01",
        },
        headers=_hdr("tesoreria"),
    )
    movimiento_id = r.json()["movimiento_id"]

    r_cxp = client.post(
        f"/api/v1/cobranza/movimientos-bancarios/{movimiento_id}/conciliar", headers=_hdr("cxp")
    )
    assert r_cxp.status_code == 403

    r_ok = client.post(
        f"/api/v1/cobranza/movimientos-bancarios/{movimiento_id}/conciliar",
        headers=_hdr("tesoreria"),
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["conciliado"] is True

    # Idempotente: conciliar de nuevo no falla ni cambia nada.
    r_otra_vez = client.post(
        f"/api/v1/cobranza/movimientos-bancarios/{movimiento_id}/conciliar",
        headers=_hdr("tesoreria"),
    )
    assert r_otra_vez.status_code == 200
    assert r_otra_vez.json()["conciliado"] is True


def test_todas_las_areas_leen_movimientos_bancarios(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    for area in ("ventas", "facturacion", "tesoreria", "cxc", "cxp", "direccion", "nominas"):
        r = client.get("/api/v1/cobranza/movimientos-bancarios", headers=_hdr(area))
        assert r.status_code == 200, f"{area} debería poder leer, dio {r.status_code}"
