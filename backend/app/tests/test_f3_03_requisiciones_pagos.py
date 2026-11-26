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
from app.modules.facturacion.factura_agencia import FacturaAgencia, FacturaAgenciaOrden
from app.modules.facturacion.factura_cliente import FacturaCliente  # noqa: F401
from app.modules.facturacion.factura_vendedor import FacturaVendedor
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


def _factura_agencia(
    db: Session, cat: dict[str, uuid.UUID], _orden_id: uuid.UUID, total: Decimal
) -> uuid.UUID:
    """`_orden_id` ya no se persiste en `FacturaAgencia` (ADR nuevo: N:M vía
    `FacturaAgenciaOrden`) — se deja el parámetro para no tocar las llamadas existentes,
    estas pruebas solo verifican la exclusión por requisición, no el reparto por orden."""
    factura_id = uuid.uuid4()
    monto = (total / Decimal("1.16")).quantize(Decimal("0.01"))
    iva = (monto * Decimal("0.16")).quantize(Decimal("0.01"))
    db.add(
        FacturaAgencia(
            factura_agencia_id=factura_id,
            agencia_id=cat["agencia_id"],
            fecha_factura_agencia=date(2026, 3, 1),
            monto_factura_agencia=monto,
            iva_factura_agencia=iva,
            total_factura_agencia=(monto + iva).quantize(Decimal("0.01")),
            comision_agencia=monto,
            estatus_factura_agencia=EstatusFacturaProveedor.AUTORIZADA.value,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return factura_id


def _factura_vendedor(
    db: Session, cat: dict[str, uuid.UUID], _orden_id: uuid.UUID, total: Decimal
) -> uuid.UUID:
    """`_orden_id` ya no se persiste en `FacturaVendedor` (ADR nuevo: N:M vía
    `FacturaVendedorOrden`) — se deja el parámetro para no tocar las llamadas
    existentes, estas pruebas solo verifican la exclusión por requisición."""
    factura_id = uuid.uuid4()
    monto = (total / Decimal("1.16")).quantize(Decimal("0.01"))
    iva = (monto * Decimal("0.16")).quantize(Decimal("0.01"))
    db.add(
        FacturaVendedor(
            factura_vendedor_id=factura_id,
            vendedor_id=cat["vendedor_id"],
            fecha_factura_vendedor=date(2026, 3, 1),
            monto_factura_vendedor=monto,
            iva_factura_vendedor=iva,
            total_factura_vendedor=(monto + iva).quantize(Decimal("0.01")),
            comision_vendedor=monto,
            estatus_factura_vendedor=EstatusFacturaProveedor.AUTORIZADA.value,
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
def test_alta_comision_vendedor_ya_no_requiere_orden_ni_calcula_porcentaje(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: "Pagos vendedor" (antes "Comisión vendedor") se simplifica
    al mismo patrón que `pago_agencia` — ya no se captura `orden_id` ni `porcentaje_
    comision_vendedor` desde el alta, solo Vendedor + `FacturaVendedor` (ahora
    obligatoria). El cálculo de comisión de la spec queda sin ejecutarse por esta vía
    (no hay `orden_id` del que tomar `OrdenCliente.total`)."""
    orden_id = _orden(db, cat, "OC-CV1", Decimal("100000.00"))
    factura_id = _factura_vendedor(db, cat, orden_id, Decimal("4000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_vendedor",
            "vendedor_comision_id": str(cat["vendedor_id"]),
            "factura_vendedor_id": str(factura_id),
            "monto_requisicion": "4000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["orden_id"] is None
    # `requisicion_comision_vendedor` (el IMPORTE calculado, spec) depende de
    # `OrdenCliente.total` — sin `orden_id` no hay de dónde calcularlo, se queda en
    # None. `porcentaje_comision_vendedor` sigue sugiriéndose del catálogo del
    # vendedor (comportamiento silencioso preexistente, ya no se muestra en la UI).
    assert body["requisicion_comision_vendedor"] is None
    # ADR-283: nace directo en "autorizada" — su FacturaVendedor ya está autorizada.
    assert body["estatus_requisicion"] == "autorizada"


def test_alta_comision_vendedor_rechaza_sin_vendedor_ni_factura_vendedor(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
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
            "tipo_requisicion": "pago_afiliado",
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400


def test_alta_pago_afiliado_requiere_factura_afiliado_id(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: `factura_afiliado_id` deja de ser opcional en
    `pago_afiliado` — con `afiliado_id` pero sin factura, el alta se rechaza."""
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400


def test_alta_pago_agencia_requiere_agencia_id_y_factura_agencia_id(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: `factura_agencia_id` deja de ser opcional en
    `pago_agencia` — con `agencia_id` pero sin factura, el alta se rechaza."""
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# ADR-283 (petición del usuario, con captura): la requisición que viene de una factura
# de proveedor ya autorizada nace directo en "autorizada" — ya no hace falta volver a
# autorizarla desde Requisiciones de pago, solo falta "Marcar pagada". "Comisión
# agencia" (sin factura de origen) es la única excepción, sigue naciendo "pendiente".
# ══════════════════════════════════════════════════════════════════════════════
def test_pago_afiliado_nace_autorizada_sin_pasar_por_pendiente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = _factura_afiliado(db, cat, Decimal("5000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_id),
            "monto_requisicion": "5000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["estatus_requisicion"] == "autorizada"


def test_pago_agencia_nace_autorizada_sin_pasar_por_pendiente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-AUT-AG", Decimal("50000.00"))
    factura_id = _factura_agencia(db, cat, orden_id, Decimal("1000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "factura_agencia_id": str(factura_id),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["estatus_requisicion"] == "autorizada"


def test_comision_agencia_sigue_naciendo_pendiente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """`comision_agencia` no tiene factura de origen — nadie la autorizó antes, así que
    sigue necesitando el canal de autorización normal de Requisiciones de pago."""
    orden_id = _orden(db, cat, "OC-AUT-CA", Decimal("50000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["estatus_requisicion"] == "pendiente"


# ══════════════════════════════════════════════════════════════════════════════
# Requisicion — máquina de estados + canal dedicado de autorización (ADR-046)
# ══════════════════════════════════════════════════════════════════════════════
def _crear_requisicion_simple(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], numero: str
) -> str:
    """Tipo `comision_agencia` (sin factura de origen): es el ÚNICO tipo que sigue
    naciendo en `pendiente` (ADR-283) — los otros 3 (pago_afiliado/pago_agencia/
    comision_vendedor) ahora nacen directo en `autorizada` porque su factura de origen
    ya pasó por Dirección, así que ya no sirven para probar la máquina de estados desde
    `pendiente` con este helper genérico."""
    orden_id = _orden(db, cat, f"OC-{numero}", Decimal("50000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    return r.json()["requisicion_id"]


def test_cxp_no_puede_autorizar_por_el_canal_operativo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, db, cat, "REQ-0100")
    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "autorizada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 403


def test_direccion_autoriza_por_el_canal_dedicado(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, db, cat, "REQ-0101")
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
    req_id = _crear_requisicion_simple(client, db, cat, "REQ-0102")
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
    req_id = _crear_requisicion_simple(client, db, cat, "REQ-0103")
    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 409  # transición inválida: pendiente -> pagada no existe


def test_cancelar_desde_pendiente_y_desde_autorizada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req1 = _crear_requisicion_simple(client, db, cat, "REQ-0104")
    r1 = client.post(
        f"/api/v1/cobranza/requisiciones/{req1}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    assert r1.status_code == 200
    assert r1.json()["estatus_requisicion"] == "cancelada"

    req2 = _crear_requisicion_simple(client, db, cat, "REQ-0105")
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
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("direccion"),
    )
    assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Petición del usuario: al pagar la requisición, su factura de proveedor relacionada
# también pasa a "pagada" (pago_afiliado/pago_agencia/comision_vendedor con
# factura_vendedor_id) — comision_agencia no tiene factura que cerrar.
# ══════════════════════════════════════════════════════════════════════════════
def test_pagar_requisicion_pago_afiliado_cierra_la_factura_afiliado(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = _factura_afiliado(db, cat, Decimal("50000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_id),
            "monto_requisicion": "50000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))

    # Antes de pagar: la factura sigue "autorizada" tal cual se sembró.
    assert db.get(FacturaAfiliado, factura_id).estatus_factura_afiliado == "autorizada"

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(FacturaAfiliado, factura_id).estatus_factura_afiliado == "pagada"


def test_pagar_requisicion_pago_agencia_cierra_la_factura_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-FA1", Decimal("100000.00"))
    factura_id = _factura_agencia(db, cat, orden_id, Decimal("20000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "factura_agencia_id": str(factura_id),
            "monto_requisicion": "20000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(FacturaAgencia, factura_id).estatus_factura_agencia == "pagada"


def test_pagar_requisicion_comision_vendedor_con_factura_vendedor_id_cierra_esa_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-FV1", Decimal("100000.00"))
    factura_id = _factura_vendedor(db, cat, orden_id, Decimal("4000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_vendedor",
            "orden_id": str(orden_id),
            "vendedor_comision_id": str(cat["vendedor_id"]),
            "factura_vendedor_id": str(factura_id),
            "monto_requisicion": "4000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    req_id = r.json()["requisicion_id"]
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(FacturaVendedor, factura_id).estatus_factura_vendedor == "pagada"


# ══════════════════════════════════════════════════════════════════════════════
# Fix (petición del usuario): "Cancelar Pago a Proveedor" — una requisición ya PAGADA
# también se puede cancelar (antes terminal). Exige motivo y revierte la factura de
# proveedor relacionada a "recibida", vaciándola de órdenes.
# ══════════════════════════════════════════════════════════════════════════════
def test_cancelar_requisicion_pagada_sin_motivo_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = _factura_afiliado(db, cat, Decimal("50000.00"))
    db.commit()
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_id),
            "monto_requisicion": "50000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))
    client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )

    r_sin_motivo = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    assert r_sin_motivo.status_code == 400, r_sin_motivo.text

    r_motivo_vacio = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada", "motivo": "   "},
        headers=_hdr("cxp"),
    )
    assert r_motivo_vacio.status_code == 400, r_motivo_vacio.text

    db.expire_all()
    assert db.get(FacturaAfiliado, factura_id).estatus_factura_afiliado == "pagada"


def test_cancelar_requisicion_pagada_con_motivo_revierte_la_factura_afiliado_a_recibida(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = _factura_afiliado(db, cat, Decimal("50000.00"))
    db.commit()
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_id),
            "monto_requisicion": "50000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))
    client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada", "motivo": "Pago duplicado, se cancela."},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estatus_requisicion"] == "cancelada"
    assert r.json()["motivo_cancelacion"] == "Pago duplicado, se cancela."

    db.expire_all()
    assert db.get(FacturaAfiliado, factura_id).estatus_factura_afiliado == "recibida"
    # El monto capturado (manual en Afiliado) NO se toca — solo cambia el estatus.
    assert db.get(FacturaAfiliado, factura_id).monto_factura_afiliado == Decimal("43103.45")


def test_cancelar_requisicion_autorizada_tambien_revierte_la_factura_relacionada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """A diferencia del tipo `comision_agencia` (sin factura, ya cubierto por
    `test_cancelar_desde_pendiente_y_desde_autorizada`), `pago_agencia` SÍ tiene una
    factura de proveedor que revertir — se cancela desde `autorizada` (sin necesidad de
    llegar a `pagada`), sin exigir motivo (flujo existente, no cambia)."""
    orden_id = _orden(db, cat, "OC-REV1", Decimal("100000.00"))
    factura_id = _factura_agencia(db, cat, orden_id, Decimal("20000.00"))
    db.commit()
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "factura_agencia_id": str(factura_id),
            "monto_requisicion": "20000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    assert r.json()["estatus_requisicion"] == "autorizada"  # ADR-283: nace ahí directo

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(FacturaAgencia, factura_id).estatus_factura_agencia == "recibida"


def test_cancelar_requisicion_pagada_vacia_las_ordenes_de_la_factura_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Decisión explícita del usuario: al revertir, la factura queda SIN órdenes
    asignadas (se desvinculan) — para que esas órdenes puedan volver a aparecer en el
    combo de una factura NUEVA sin riesgo de quedar en 2 facturas vigentes a la vez."""
    orden_id = _orden(db, cat, "OC-REV2", Decimal("100000.00"))
    factura_id = _factura_agencia(db, cat, orden_id, Decimal("20000.00"))
    db.add(
        FacturaAgenciaOrden(
            id=uuid.uuid4(),
            factura_agencia_id=factura_id,
            orden_id=orden_id,
            porcentaje_comision_snap=Decimal("20.00"),
            comision_calculada=Decimal("20000.00"),
        )
    )
    db.commit()
    assert (
        db.query(FacturaAgenciaOrden)
        .filter(FacturaAgenciaOrden.factura_agencia_id == factura_id)
        .count()
        == 1
    )

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "factura_agencia_id": str(factura_id),
            "monto_requisicion": "20000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada", "motivo": "Pago a proveedor cancelado."},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(FacturaAgencia, factura_id).estatus_factura_agencia == "recibida"
    assert (
        db.query(FacturaAgenciaOrden)
        .filter(FacturaAgenciaOrden.factura_agencia_id == factura_id)
        .count()
        == 0
    )


def test_cancelar_requisicion_ya_cancelada_es_idempotente_no_vuelve_a_pedir_motivo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    req_id = _crear_requisicion_simple(client, db, cat, "REQ-IDEMP")
    client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "cancelada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estatus_requisicion"] == "cancelada"


# ══════════════════════════════════════════════════════════════════════════════
# Fix (petición del usuario): columna "Órdenes" en la lista — folios relacionados,
# también buscable.
# ══════════════════════════════════════════════════════════════════════════════
def test_lista_requisiciones_resuelve_folios_de_ordenes_y_se_puede_buscar_por_ellos(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-ORD-COL1", Decimal("100000.00"))
    factura_id = _factura_agencia(db, cat, orden_id, Decimal("20000.00"))
    db.add(
        FacturaAgenciaOrden(
            id=uuid.uuid4(),
            factura_agencia_id=factura_id,
            orden_id=orden_id,
            porcentaje_comision_snap=Decimal("20.00"),
            comision_calculada=Decimal("20000.00"),
        )
    )
    db.commit()
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "factura_agencia_id": str(factura_id),
            "monto_requisicion": "20000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]

    detalle = client.get(f"/api/v1/cobranza/requisiciones/{req_id}", headers=_hdr("cxp")).json()
    assert detalle["ordenes_folios"] == "OC-ORD-COL1"

    lista = client.get(
        "/api/v1/cobranza/requisiciones", params={"q": "OC-ORD-COL1"}, headers=_hdr("cxp")
    ).json()
    assert any(f["requisicion_id"] == req_id for f in lista["items"])
    assert lista["items"][0]["ordenes_folios"] == "OC-ORD-COL1"


def test_alta_comision_vendedor_rechaza_sin_factura_vendedor(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: `factura_vendedor_id` ya NO es opcional para
    `comision_vendedor` (antes sí lo era) — sin ella, el alta se rechaza."""
    orden_id = _orden(db, cat, "OC-FV2", Decimal("100000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_vendedor",
            "orden_id": str(orden_id),
            "vendedor_comision_id": str(cat["vendedor_id"]),
            "monto_requisicion": "4000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400


def test_pagar_requisicion_comision_agencia_no_truena_sin_factura_que_cerrar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """`comision_agencia` nunca tiene una factura asociada (confirmado: es un pago puro,
    sin entidad "factura" que cerrar) — pagarla no debe tronar."""
    orden_id = _orden(db, cat, "OC-CA1", Decimal("100000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_agencia",
            "orden_id": str(orden_id),
            "agencia_id": str(cat["agencia_id"]),
            "monto_requisicion": "2000.00",
        },
        headers=_hdr("cxp"),
    )
    req_id = r.json()["requisicion_id"]
    client.post(f"/api/v1/cobranza/requisiciones/{req_id}/autorizar", headers=_hdr("direccion"))

    r = client.post(
        f"/api/v1/cobranza/requisiciones/{req_id}/estatus",
        json={"estatus": "pagada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estatus_requisicion"] == "pagada"


# ══════════════════════════════════════════════════════════════════════════════
# Combos "disponibles" del alta — petición del usuario, con captura: una factura ya
# usada por OTRA requisición (de cualquier estatus) no debe volver a ofrecerse.
# ══════════════════════════════════════════════════════════════════════════════
def test_facturas_afiliado_disponibles_excluye_las_ya_usadas_por_una_requisicion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_libre = _factura_afiliado(db, cat, Decimal("5000.00"))
    factura_usada = _factura_afiliado(db, cat, Decimal("6000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_usada),
            "monto_requisicion": "6000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text

    ruta = "/api/v1/cobranza/requisiciones/facturas-afiliado-disponibles"
    r = client.get(ruta, headers=_hdr("cxp"))
    assert r.status_code == 200, r.text
    ids = {item["factura_afiliado_id"] for item in r.json()}
    assert str(factura_libre) in ids
    assert str(factura_usada) not in ids


def test_facturas_agencia_disponibles_excluye_las_ya_usadas_por_una_requisicion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-DISP-AG", Decimal("100000.00"))
    factura_libre = _factura_agencia(db, cat, orden_id, Decimal("5000.00"))
    factura_usada = _factura_agencia(db, cat, orden_id, Decimal("6000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "factura_agencia_id": str(factura_usada),
            "monto_requisicion": "6000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text

    ruta = "/api/v1/cobranza/requisiciones/facturas-agencia-disponibles"
    r = client.get(ruta, headers=_hdr("cxp"))
    assert r.status_code == 200, r.text
    ids = {item["factura_agencia_id"] for item in r.json()}
    assert str(factura_libre) in ids
    assert str(factura_usada) not in ids


def test_facturas_vendedor_disponibles_excluye_las_ya_usadas_por_una_requisicion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "OC-DISP-VD", Decimal("100000.00"))
    factura_libre = _factura_vendedor(db, cat, orden_id, Decimal("5000.00"))
    factura_usada = _factura_vendedor(db, cat, orden_id, Decimal("6000.00"))
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "comision_vendedor",
            "vendedor_comision_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "factura_vendedor_id": str(factura_usada),
            "monto_requisicion": "6000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text

    ruta = "/api/v1/cobranza/requisiciones/facturas-vendedor-disponibles"
    r = client.get(ruta, headers=_hdr("cxp"))
    assert r.status_code == 200, r.text
    ids = {item["factura_vendedor_id"] for item in r.json()}
    assert str(factura_libre) in ids
    assert str(factura_usada) not in ids


# ══════════════════════════════════════════════════════════════════════════════
# ADR-282 (petición del usuario, con captura): número automático + folio de origen
# ══════════════════════════════════════════════════════════════════════════════
def test_numero_requisicion_se_genera_automatico_con_formato_rq_anio_mes_consecutivo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1 = _factura_afiliado(db, cat, Decimal("5000.00"))
    factura_2 = _factura_afiliado(db, cat, Decimal("6000.00"))
    db.commit()

    r1 = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_1),
            "monto_requisicion": "5000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r1.status_code == 201, r1.text
    numero_1 = r1.json()["numero_requisicion"]
    hoy = date.today()
    prefijo = f"RQ-{hoy.year}-{hoy.month:02d}-"
    assert numero_1.startswith(prefijo)

    r2 = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_2),
            "monto_requisicion": "6000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r2.status_code == 201, r2.text
    numero_2 = r2.json()["numero_requisicion"]
    assert int(numero_2.removeprefix(prefijo)) == int(numero_1.removeprefix(prefijo)) + 1


def test_crear_requisicion_con_numero_requisicion_en_el_payload_se_rechaza(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    """`numero_requisicion` es "Calculado" (ADR-282): el esquema tiene `extra="forbid"`,
    así que mandarlo desde el cliente es un 422, no se ignora en silencio."""
    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "numero_requisicion": "RQ-2026-01-1",
            "tipo_requisicion": "comision_agencia",
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(uuid.uuid4()),
            "monto_requisicion": "1000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 422


def test_crear_requisicion_rechaza_factura_afiliado_no_autorizada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = uuid.uuid4()
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=factura_id,
            afiliado_id=cat["afiliado_id"],
            factura_emisora="AF-RECIBIDA",
            fecha_factura_afiliado=date(2026, 3, 1),
            monto_factura_afiliado=Decimal("1000.00"),
            iva_factura_afiliado=Decimal("160.00"),
            total_factura_afiliado=Decimal("1160.00"),
            estatus_factura_afiliado="recibida",
            created_by=ADMIN_ID,
        )
    )
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_id),
            "monto_requisicion": "1160.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_crear_requisicion_rechaza_factura_afiliado_ya_usada_por_otra_requisicion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = _factura_afiliado(db, cat, Decimal("5000.00"))
    db.commit()
    payload = {
        "tipo_requisicion": "pago_afiliado",
        "afiliado_id": str(cat["afiliado_id"]),
        "factura_afiliado_id": str(factura_id),
        "monto_requisicion": "5000.00",
    }
    r1 = client.post("/api/v1/cobranza/requisiciones", json=payload, headers=_hdr("cxp"))
    assert r1.status_code == 201, r1.text

    r2 = client.post("/api/v1/cobranza/requisiciones", json=payload, headers=_hdr("cxp"))
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["codigo"] == "conflicto"


def test_listado_expone_y_busca_por_folio_de_la_factura_de_origen(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id = uuid.uuid4()
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=factura_id,
            afiliado_id=cat["afiliado_id"],
            factura_emisora="EMI-FOLIO-BUSQUEDA",
            fecha_factura_afiliado=date(2026, 3, 1),
            monto_factura_afiliado=Decimal("1000.00"),
            iva_factura_afiliado=Decimal("160.00"),
            total_factura_afiliado=Decimal("1160.00"),
            estatus_factura_afiliado=EstatusFacturaProveedor.AUTORIZADA.value,
            created_by=ADMIN_ID,
        )
    )
    db.commit()

    r = client.post(
        "/api/v1/cobranza/requisiciones",
        json={
            "tipo_requisicion": "pago_afiliado",
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_afiliado_id": str(factura_id),
            "monto_requisicion": "1160.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    req_id = r.json()["requisicion_id"]
    assert r.json()["folio_factura_origen"] == "EMI-FOLIO-BUSQUEDA"

    r_get = client.get(f"/api/v1/cobranza/requisiciones/{req_id}", headers=_hdr("cxp"))
    assert r_get.json()["folio_factura_origen"] == "EMI-FOLIO-BUSQUEDA"

    r_q = client.get(
        "/api/v1/cobranza/requisiciones", params={"q": "FOLIO-BUSQUEDA"}, headers=_hdr("cxp")
    )
    assert r_q.status_code == 200, r_q.text
    ids = {item["requisicion_id"] for item in r_q.json()["items"]}
    assert req_id in ids

    r_vacio = client.get(
        "/api/v1/cobranza/requisiciones", params={"q": "NO-EXISTE-XYZ"}, headers=_hdr("cxp")
    )
    assert r_vacio.json()["items"] == []


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
