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
from sqlalchemy import create_engine, select
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
from app.modules.ordenes.orden_cliente import OrdenCliente
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


# ADR-285 (petición del usuario, con captura): paginación real de "Órdenes de Servicio" —
# la búsqueda ahora también cubre el nombre del anunciante, y el listado trae `oe_count`
# (antes el frontend traía TODAS las OE para contarlas en memoria).
def test_busqueda_incluye_nombre_de_anunciante(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/ordenes/clientes", params={"q": "Anunciante Uno"}, headers=_hdr("ventas")
    )
    assert r.json()["total"] == 1
    r_vacio = client.get(
        "/api/v1/ordenes/clientes", params={"q": "No Existe SA"}, headers=_hdr("ventas")
    )
    assert r_vacio.json()["total"] == 0


def test_listado_expone_oe_count_en_lote(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get("/api/v1/ordenes/clientes", headers=_hdr("ventas"))
    assert r.json()["items"][0]["oe_count"] == 1


def test_obtener_orden_cliente_expone_oe_count(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(f"/api/v1/ordenes/clientes/{datos['orden_id']}", headers=_hdr("ventas"))
    assert r.json()["oe_count"] == 1


def test_filtro_listas_para_cerrar(
    client: TestClient, db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """La orden sembrada ('capturada', 1 OE 'cerrada') no califica: su `estatus_orden`
    no está en gestión de estaciones todavía. Se agregan 2 órdenes nuevas: una SÍ
    califica (en_transmision, su única OE ya cerrada) y otra NO (en_verificacion, pero
    con una OE todavía sin cerrar)."""
    oc_lista = OrdenCliente(
        orden_id=uuid.uuid4(),
        folio_orden="OC-2026-0002",
        numero_orden_cliente="NUM-002",
        fecha_venta=date(2026, 1, 10),
        anio_venta=2026,
        mes_venta=1,
        empresa_facturadora_id=db.scalar(
            select(EmpresaFacturadora.empresa_facturadora_id)
        ),
        vendedor_principal_id=db.scalar(select(Vendedor.vendedor_id)),
        anunciante_id=db.scalar(select(Anunciante.anunciante_id)),
        fecha_inicio_campania=date(2026, 2, 1),
        fecha_fin_campania=date(2026, 2, 28),
        total_dias_campania=28,
        precio_unitario=Decimal("1000.00"),
        total_spots=10,
        subtotal=Decimal("10000.00"),
        iva=Decimal("1600.00"),
        total=Decimal("11600.00"),
        estatus_orden="en_transmision",
        created_by=ADMIN_ID,
    )
    oc_no_lista = OrdenCliente(
        orden_id=uuid.uuid4(),
        folio_orden="OC-2026-0003",
        numero_orden_cliente="NUM-003",
        fecha_venta=date(2026, 1, 10),
        anio_venta=2026,
        mes_venta=1,
        empresa_facturadora_id=oc_lista.empresa_facturadora_id,
        vendedor_principal_id=oc_lista.vendedor_principal_id,
        anunciante_id=oc_lista.anunciante_id,
        fecha_inicio_campania=date(2026, 2, 1),
        fecha_fin_campania=date(2026, 2, 28),
        total_dias_campania=28,
        precio_unitario=Decimal("1000.00"),
        total_spots=10,
        subtotal=Decimal("10000.00"),
        iva=Decimal("1600.00"),
        total=Decimal("11600.00"),
        estatus_orden="en_verificacion",
        created_by=ADMIN_ID,
    )
    db.add_all([oc_lista, oc_no_lista])
    db.flush()

    def _oe(orden_id: uuid.UUID, folio: str, estatus: str) -> None:
        db.add(
            OrdenEstacion(
                orden_estacion_id=uuid.uuid4(),
                folio_orden_estacion=folio,
                orden_id=orden_id,
                anunciante_id=oc_lista.anunciante_id,
                vendedor_id=oc_lista.vendedor_principal_id,
                estacion_id=datos["estacion_id"],
                plaza_id=db.scalar(select(Plaza.plaza_id)),
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
                estatus=estatus,
                created_by=ADMIN_ID,
            )
        )

    _oe(oc_lista.orden_id, "OE-2026-0002A", "cerrada")
    _oe(oc_no_lista.orden_id, "OE-2026-0003A", "en_transmision")
    db.commit()

    r = client.get(
        "/api/v1/ordenes/clientes",
        params={"listas_para_cerrar": "true"},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["folio_orden"] == "OC-2026-0002"


def test_listado_ordena_por_fecha_de_creacion_mas_reciente_primero(
    client: TestClient, db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """ADR-285: al quitarle al frontend su propio `.sort()` sobre el arreglo completo
    (ahora pagina contra el backend), el orden natural de la consulta debe ser el mismo
    que el usuario ya veía — más reciente primero, no por folio como texto (ADR-275)."""
    from datetime import datetime

    vieja = OrdenCliente(
        orden_id=uuid.uuid4(),
        folio_orden="OC-2026-0005",
        numero_orden_cliente="NUM-VIEJA",
        fecha_venta=date(2026, 1, 1),
        anio_venta=2026,
        mes_venta=1,
        empresa_facturadora_id=db.scalar(select(EmpresaFacturadora.empresa_facturadora_id)),
        vendedor_principal_id=db.scalar(select(Vendedor.vendedor_id)),
        anunciante_id=db.scalar(select(Anunciante.anunciante_id)),
        fecha_inicio_campania=date(2026, 2, 1),
        fecha_fin_campania=date(2026, 2, 28),
        total_dias_campania=28,
        precio_unitario=Decimal("1000.00"),
        total_spots=10,
        subtotal=Decimal("10000.00"),
        iva=Decimal("1600.00"),
        total=Decimal("11600.00"),
        estatus_orden="capturada",
        created_by=ADMIN_ID,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    nueva = OrdenCliente(
        orden_id=uuid.uuid4(),
        folio_orden="OC-2026-0041",
        numero_orden_cliente="NUM-NUEVA",
        fecha_venta=date(2026, 1, 1),
        anio_venta=2026,
        mes_venta=1,
        empresa_facturadora_id=vieja.empresa_facturadora_id,
        vendedor_principal_id=vieja.vendedor_principal_id,
        anunciante_id=vieja.anunciante_id,
        fecha_inicio_campania=date(2026, 2, 1),
        fecha_fin_campania=date(2026, 2, 28),
        total_dias_campania=28,
        precio_unitario=Decimal("1000.00"),
        total_spots=10,
        subtotal=Decimal("10000.00"),
        iva=Decimal("1600.00"),
        total=Decimal("11600.00"),
        estatus_orden="capturada",
        created_by=ADMIN_ID,
        created_at=datetime(2026, 6, 15, 10, 0, 0),
    )
    db.add_all([vieja, nueva])
    db.commit()

    r = client.get("/api/v1/ordenes/clientes", headers=_hdr("ventas"))
    folios = [it["folio_orden"] for it in r.json()["items"]]
    # "OC-2026-0041" (nueva) antes que "OC-2026-0005" (vieja), aunque el folio como
    # texto diga lo contrario ("0005" < "0041").
    assert folios.index("OC-2026-0041") < folios.index("OC-2026-0005")


def test_filtro_activas_excluye_facturada_cobrada_cancelada(
    client: TestClient, db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """La orden sembrada ('capturada') SÍ es activa. Se agrega una 'cobrada' (no
    activa) para confirmar que el filtro la excluye."""
    db.add(
        OrdenCliente(
            orden_id=uuid.uuid4(),
            folio_orden="OC-2026-0099",
            numero_orden_cliente="NUM-099",
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=db.scalar(select(EmpresaFacturadora.empresa_facturadora_id)),
            vendedor_principal_id=db.scalar(select(Vendedor.vendedor_id)),
            anunciante_id=db.scalar(select(Anunciante.anunciante_id)),
            fecha_inicio_campania=date(2026, 2, 1),
            fecha_fin_campania=date(2026, 2, 28),
            total_dias_campania=28,
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=Decimal("10000.00"),
            iva=Decimal("1600.00"),
            total=Decimal("11600.00"),
            estatus_orden="cobrada",
            created_by=ADMIN_ID,
        )
    )
    db.commit()

    r = client.get("/api/v1/ordenes/clientes", params={"activas": "true"}, headers=_hdr("ventas"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["folio_orden"] == "OC-2026-0001"


def test_obtener_orden_cliente(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(f"/api/v1/ordenes/clientes/{datos['orden_id']}", headers=_hdr("facturacion"))
    assert r.status_code == 200
    assert r.json()["orden_id"] == str(datos["orden_id"])


def test_obtener_orden_cliente_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/ordenes/clientes/{uuid.uuid4()}", headers=_hdr("ventas"))
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "no_encontrado"


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


# ADR-285 (petición del usuario, con captura): paginación real de "Órdenes de
# Transmisión"/"Verificaciones" — la búsqueda ahora también cubre nombre de estación,
# nombre de afiliado y folio de la OC de origen (antes el frontend lo hacía en memoria
# sobre el arreglo completo), y hay un filtro nuevo `tiene_incidencias`.
@pytest.mark.parametrize(
    "termino", ["XHTEST-FM", "Afiliado Uno", "OC-2026-0001", "OE-2026-0001A"]
)
def test_busqueda_de_orden_estacion_cubre_estacion_afiliado_y_oc_origen(
    client: TestClient, datos: dict[str, uuid.UUID], termino: str
) -> None:
    r = client.get("/api/v1/ordenes/estaciones", params={"q": termino}, headers=_hdr("tesoreria"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["orden_estacion_id"] == str(datos["oe_id"])


def test_busqueda_de_orden_estacion_sin_coincidencia(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/ordenes/estaciones", params={"q": "No Existe"}, headers=_hdr("tesoreria")
    )
    assert r.json()["total"] == 0


def test_filtro_tiene_incidencias(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r_con = client.get(
        "/api/v1/ordenes/estaciones",
        params={"tiene_incidencias": "true"},
        headers=_hdr("tesoreria"),
    )
    assert r_con.json()["total"] == 1
    assert r_con.json()["items"][0]["orden_estacion_id"] == str(datos["oe_id"])

    r_sin = client.get(
        "/api/v1/ordenes/estaciones",
        params={"tiene_incidencias": "false"},
        headers=_hdr("tesoreria"),
    )
    assert r_sin.json()["total"] == 0


def test_listado_ordena_por_fecha_de_creacion_mas_reciente_primero_oe(
    client: TestClient, db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """ADR-285: mismo fix que `test_listado_ordena_por_fecha_de_creacion_mas_reciente_primero`
    (OrdenCliente), pero para OrdenEstacion — el frontend ya no reordena "Órdenes de
    Transmisión" en el cliente, así que el orden natural de la consulta debe ser más
    reciente primero."""
    from datetime import datetime

    oe_existente = db.get(OrdenEstacion, datos["oe_id"])
    assert oe_existente is not None

    vieja = OrdenEstacion(
        orden_estacion_id=uuid.uuid4(),
        folio_orden_estacion="OE-2026-0002A",
        orden_id=datos["orden_id"],
        anunciante_id=oe_existente.anunciante_id,
        vendedor_id=oe_existente.vendedor_id,
        estacion_id=datos["estacion_id"],
        plaza_id=oe_existente.plaza_id,
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
        created_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    nueva = OrdenEstacion(
        orden_estacion_id=uuid.uuid4(),
        folio_orden_estacion="OE-2026-0003A",
        orden_id=datos["orden_id"],
        anunciante_id=oe_existente.anunciante_id,
        vendedor_id=oe_existente.vendedor_id,
        estacion_id=datos["estacion_id"],
        plaza_id=oe_existente.plaza_id,
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
        created_at=datetime(2026, 6, 15, 10, 0, 0),
    )
    db.add_all([vieja, nueva])
    db.commit()

    r = client.get("/api/v1/ordenes/estaciones", headers=_hdr("tesoreria"))
    folios = [it["folio_orden_estacion"] for it in r.json()["items"]]
    # "OE-2026-0003A" (nueva) antes que "OE-2026-0002A" (vieja), aunque el folio como
    # texto diga lo contrario.
    assert folios.index("OE-2026-0003A") < folios.index("OE-2026-0002A")


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
