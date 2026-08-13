"""Pruebas F1-03 · API de lectura de Órdenes (SQLite).

Cubre los endpoints `GET` nuevos (Tanda 3 — solo lectura; Create/Update llegan en la
Tanda 5): paginación/filtros, 404, y RBAC de la matriz "Órdenes" (propuesta §9): Ventas
captura (implica lectura), Facturación/Tesorería/CxC/CxP/Dirección/Admin solo leen,
Nóminas sin acceso.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, time
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
from app.modules.catalogos.agencia import (
    Agencia,  # noqa: F401 — registra la tabla (FK de OrdenCliente)
)
from app.modules.catalogos.anunciante import Anunciante, Marca  # noqa: F401 — Marca ídem
from app.modules.catalogos.categoria import Categoria  # noqa: F401 — ídem
from app.modules.catalogos.contrato import Contrato  # noqa: F401 — ídem
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.incidencia import Incidencia
from app.modules.ordenes.orden_cliente import ITEMS_VOBO, OrdenCliente, OrdenClienteVoBoItem
from app.modules.ordenes.orden_estacion import OrdenEstacion, OrdenEstacionDia
from app.modules.ordenes.router import router as ordenes_router
from app.modules.ordenes.verificacion import Verificacion
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


@pytest.fixture
def datos(db: Session) -> dict[str, uuid.UUID]:
    """Siembra el mínimo indispensable: 1 OrdenCliente con 1 OrdenEstacion, 1 día,
    1 Verificacion y 1 Incidencia — suficiente para ejercitar todos los endpoints."""
    db.add(
        Usuario(
            usuario_id=ADMIN_ID,
            nombre_usuario="Admin",
            email="admin@grcoir.com",
            area="admin",
        )
    )
    plaza_id = uuid.uuid4()
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="CDMX"))
    afiliado_id = uuid.uuid4()
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="Afiliado Uno",
            razon_social_afiliado="Afiliado Uno SA de CV",
            rfc_afiliado="AUN900101AB1",
            plaza_id=plaza_id,
        )
    )
    estacion_id = uuid.uuid4()
    db.add(
        Estacion(
            estacion_id=estacion_id,
            afiliado_id=afiliado_id,
            plaza_id=plaza_id,
            nombre_estacion="XHTEST-FM",
            tipo_senal="fm",
        )
    )
    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
        )
    )
    vendedor_id = uuid.uuid4()
    db.add(Vendedor(vendedor_id=vendedor_id, nombre_vendedor="Vendedor Uno"))
    anunciante_id = uuid.uuid4()
    db.add(
        Anunciante(
            anunciante_id=anunciante_id,
            nombre_comercial="Anunciante Uno",
            nombre_fiscal="Anunciante Uno SA de CV",
            rfc_anunciante="ANU900101AB1",
        )
    )
    db.flush()

    orden_id = uuid.uuid4()
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden="OC-2026-0001",
            numero_orden_cliente="NUM-001",
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=empresa_id,
            vendedor_principal_id=vendedor_id,
            anunciante_id=anunciante_id,
            fecha_inicio_campania=date(2026, 2, 1),
            fecha_fin_campania=date(2026, 2, 28),
            total_dias_campania=28,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=Decimal("10000.00"),
            iva=Decimal("1600.00"),
            total=Decimal("11600.00"),
            estatus_orden="capturada",
            created_by=ADMIN_ID,
        )
    )
    for item in ITEMS_VOBO:
        db.add(
            OrdenClienteVoBoItem(
                orden_cliente_vobo_item_id=uuid.uuid4(),
                orden_id=orden_id,
                item_clave=item,
                completado=item in ("razon_social", "plaza"),
            )
        )

    oe_id = uuid.uuid4()
    db.add(
        OrdenEstacion(
            orden_estacion_id=oe_id,
            folio_orden_estacion="OE-2026-0001A",
            orden_id=orden_id,
            anunciante_id=anunciante_id,
            vendedor_id=vendedor_id,
            estacion_id=estacion_id,
            plaza_id=plaza_id,
            duracion_spot="30s",
            precio_spot=Decimal("1000.00"),
            importe_estacion=Decimal("10000.00"),
            porcentaje_participacion_oir=Decimal("30.00"),
            importe_oir=Decimal("3000.00"),
            iva_oir=Decimal("480.00"),
            total_oir=Decimal("3480.00"),
            importe_emisora=Decimal("7000.00"),
            iva_emisora=Decimal("1120.00"),
            total_emisora=Decimal("8120.00"),
            estatus="cerrada",
            created_by=ADMIN_ID,
        )
    )
    dia_id = uuid.uuid4()
    db.add(
        OrdenEstacionDia(
            orden_estacion_dia_id=dia_id,
            orden_estacion_id=oe_id,
            fecha_transmision=date(2026, 2, 1),
            hora_inicio=time(7, 0),
            hora_fin=time(9, 0),
            spots_solicitados=10,
            spots_asignados=10,
            spots_programados=10,
        )
    )
    verificacion_id = uuid.uuid4()
    db.add(
        Verificacion(
            verificacion_id=verificacion_id,
            orden_estacion_dia_id=dia_id,
            spots_verificados=8,
            fecha_verificacion=date(2026, 2, 1),
            reconciliada=True,
            created_by=ADMIN_ID,
        )
    )
    db.add(
        Incidencia(
            incidencia_id=uuid.uuid4(),
            verificacion_id=verificacion_id,
            orden_estacion_id=oe_id,
            tipo_incidencia="faltante",
            spots_ordenados=10,
            spots_ejecutados=8,
            diferencia_spots=-2,
            descripcion_incidencia="2 spots no transmitidos.",
            fecha_incidencia=date(2026, 2, 1),
            monto_ajuste=Decimal("-2000.00"),
        )
    )
    db.commit()
    return {"orden_id": orden_id, "oe_id": oe_id, "dia_id": dia_id, "estacion_id": estacion_id}


@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(ordenes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


# ── OrdenCliente ──────────────────────────────────────────────────────────────
def test_listar_ordenes_cliente(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get("/api/v1/ordenes/clientes", headers=_hdr("ventas"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["folio_orden"] == "OC-2026-0001"
    assert body["items"][0]["subtotal"] == "10000.00"  # Decimal como string (ADR-015)


def test_filtro_estatus_orden(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(
        "/api/v1/ordenes/clientes", params={"estatus_orden": "cobrada"}, headers=_hdr("ventas")
    )
    assert r.json()["total"] == 0
    r = client.get(
        "/api/v1/ordenes/clientes", params={"estatus_orden": "capturada"}, headers=_hdr("ventas")
    )
    assert r.json()["total"] == 1


def test_obtener_orden_cliente(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(f"/api/v1/ordenes/clientes/{datos['orden_id']}", headers=_hdr("facturacion"))
    assert r.status_code == 200
    assert r.json()["orden_id"] == str(datos["orden_id"])


def test_obtener_orden_cliente_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/ordenes/clientes/{uuid.uuid4()}", headers=_hdr("ventas"))
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "no_encontrado"


def test_vobo_orden_cliente(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(f"/api/v1/ordenes/clientes/{datos['orden_id']}/vobo", headers=_hdr("ventas"))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == len(ITEMS_VOBO)
    completados = {i["item_clave"] for i in items if i["completado"]}
    assert completados == {"razon_social", "plaza"}


def test_historial_comisiones_orden_cliente_vacio(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        f"/api/v1/ordenes/clientes/{datos['orden_id']}/historial-comisiones",
        headers=_hdr("direccion"),
    )
    assert r.status_code == 200
    assert r.json() == []


# ── OrdenEstacion ─────────────────────────────────────────────────────────────
def test_listar_ordenes_estacion_filtra_por_orden(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/ordenes/estaciones",
        params={"orden_id": str(datos["orden_id"])},
        headers=_hdr("tesoreria"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["orden_estacion_id"] == str(datos["oe_id"])
    assert body["items"][0]["importe_oir"] == "3000.00"


def test_listar_dias_orden_estacion(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(f"/api/v1/ordenes/estaciones/{datos['oe_id']}/dias", headers=_hdr("cxc"))
    assert r.status_code == 200
    dias = r.json()
    assert len(dias) == 1
    assert dias[0]["orden_estacion_dia_id"] == str(datos["dia_id"])


# ── Verificacion ──────────────────────────────────────────────────────────────
def test_listar_verificaciones_por_orden_estacion(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/ordenes/verificaciones",
        params={"orden_estacion_id": str(datos["oe_id"])},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["spots_verificados"] == 8


# ── Incidencia ────────────────────────────────────────────────────────────────
def test_listar_incidencias_filtra_por_tipo(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/ordenes/incidencias", params={"tipo_incidencia": "faltante"}, headers=_hdr("admin")
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r_vacio = client.get(
        "/api/v1/ordenes/incidencias",
        params={"tipo_incidencia": "excedente"},
        headers=_hdr("admin"),
    )
    assert r_vacio.json()["total"] == 0


# ── RBAC de la matriz "Órdenes" (propuesta §9) ────────────────────────────────
def test_nominas_no_tiene_acceso(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get("/api/v1/ordenes/clientes", headers=_hdr("nominas"))
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "sin_permiso"


@pytest.mark.parametrize(
    "area", ["ventas", "facturacion", "tesoreria", "cxc", "cxp", "direccion", "admin"]
)
def test_areas_con_lectura_pueden_listar(
    client: TestClient, datos: dict[str, uuid.UUID], area: str
) -> None:
    r = client.get("/api/v1/ordenes/clientes", headers=_hdr(area))
    assert r.status_code == 200
