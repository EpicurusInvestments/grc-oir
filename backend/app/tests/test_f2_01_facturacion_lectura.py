"""Pruebas F2 · Tanda 1 — modelo + API de lectura de Facturación (SQLite).

Cubre lo que la Tanda 1 entrega: que el esquema de las 5 entidades es correcto (incluidas
las restricciones que se pidieron revisar: los CHECK de `ROUND(x, 2)` y las 2 UNIQUE), que
los `GET` listan/filtran/404ean, y que el RBAC de las DOS claves del módulo
(`facturacion` para FacturaCliente, `costos` para las otras tres) se comporta como la
ficha del módulo especifica.

La captura, las máquinas de estado y el handoff `timbrada → OrdenCliente.facturada`
llegan en la Tanda 2: aquí las filas se insertan directo por ORM.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.categoria import Categoria  # noqa: F401 — registra la tabla (FK de OC)
from app.modules.catalogos.contrato import Contrato  # noqa: F401 — ídem
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.facturacion.costo_adicional import CostoAdicional
from app.modules.facturacion.factura_afiliado import FacturaAfiliado, FacturaAfiliadoOrden
from app.modules.facturacion.factura_agencia import FacturaAgencia
from app.modules.facturacion.factura_cliente import FacturaCliente
from app.modules.facturacion.router import router as facturacion_router
from app.modules.ordenes.orden_cliente import OrdenCliente
from app.modules.ordenes.orden_estacion import OrdenEstacion
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
    """Cadena mínima F0 → F1 → F2: catálogos, una OC cerrada con su OE cerrada, y una
    fila de cada entidad de F2."""
    db.add(
        Usuario(
            usuario_id=ADMIN_ID, nombre_usuario="Admin", email="admin@grcoir.com", area="admin"
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
    agencia_id = uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=agencia_id,
            nombre_agencia="Agencia Uno",
            rfc_agencia="AGU900101AB1",
        )
    )
    cuenta_id = uuid.uuid4()
    db.add(
        CuentaContable(
            cuenta_contable_id=cuenta_id,
            codigo_cuenta="4100-001",
            nombre_cuenta="Ingresos por transmisión",
            tipo_cuenta="ingreso",
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
            agencia_id=agencia_id,
            fecha_inicio_campania=date(2026, 2, 1),
            fecha_fin_campania=date(2026, 2, 28),
            total_dias_campania=28,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=Decimal("10000.00"),
            iva=Decimal("1600.00"),
            total=Decimal("11600.00"),
            estatus_orden="orden_cerrada",
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
    db.flush()

    factura_id = uuid.uuid4()
    db.add(
        FacturaCliente(
            factura_id=factura_id,
            numero_factura="F-0001",
            orden_id=orden_id,
            empresa_facturadora_id=empresa_id,
            anunciante_id=anunciante_id,
            agencia_id=agencia_id,
            razon_social_facturacion="Agencia Uno SA de CV",
            rfc_facturacion="AGU900101AB1",
            descripcion_factura="Servicios de transmisión febrero 2026",
            fecha_inicio_transmision=date(2026, 2, 1),
            fecha_fin_transmision=date(2026, 2, 28),
            fecha_factura=date(2026, 3, 1),
            subtotal_factura=Decimal("10000.00"),
            iva_factura=Decimal("1600.00"),
            total_factura=Decimal("11600.00"),
            cuenta_contable_id=cuenta_id,
            metodo_pago_clave="PUE",
            estado_facturacion="preparada",
            created_by=ADMIN_ID,
        )
    )
    fa_id = uuid.uuid4()
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=fa_id,
            afiliado_id=afiliado_id,
            razon_social_afiliada="Afiliado Uno SA de CV",
            factura_emisora="AF-77",
            fecha_factura_afiliado=date(2026, 3, 2),
            monto_factura_afiliado=Decimal("7000.00"),
            iva_factura_afiliado=Decimal("1120.00"),
            total_factura_afiliado=Decimal("8120.00"),
            estatus_factura_afiliado="recibida",
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    db.add(
        FacturaAfiliadoOrden(
            id=uuid.uuid4(),
            factura_afiliado_id=fa_id,
            orden_estacion_id=oe_id,
            monto_asignado=Decimal("7000.00"),
            notas_asignacion="Total de la OE",
        )
    )
    fag_id = uuid.uuid4()
    db.add(
        FacturaAgencia(
            factura_agencia_id=fag_id,
            agencia_id=agencia_id,
            orden_id=orden_id,
            folio_factura_agencia="AG-55",
            fecha_factura_agencia=date(2026, 3, 3),
            monto_factura_agencia=Decimal("1160.00"),
            iva_factura_agencia=Decimal("185.60"),
            total_factura_agencia=Decimal("1345.60"),
            porcentaje_comision_agencia=Decimal("10.00"),
            comision_agencia=Decimal("1160.00"),
            estatus_factura_agencia="recibida",
            created_by=ADMIN_ID,
        )
    )
    costo_id = uuid.uuid4()
    db.add(
        CostoAdicional(
            costo_id=costo_id,
            tipo_costo="nomina",
            orden_id=None,
            descripcion_costo="Nómina operativa febrero",
            periodo_contable="2026-02",
            monto_costo=Decimal("50000.00"),
            created_by=ADMIN_ID,
        )
    )
    db.commit()
    return {
        "orden_id": orden_id,
        "oe_id": oe_id,
        "factura_id": factura_id,
        "factura_afiliado_id": fa_id,
        "factura_agencia_id": fag_id,
        "costo_id": costo_id,
        "afiliado_id": afiliado_id,
        "agencia_id": agencia_id,
        "empresa_id": empresa_id,
        "anunciante_id": anunciante_id,
        "cuenta_id": cuenta_id,
    }


@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(facturacion_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


# ── Esquema: las restricciones que se revisaron a mano ────────────────────────
def test_factura_cliente_es_1_a_1_con_la_orden(db: Session, datos: dict[str, uuid.UUID]) -> None:
    """`uq_factura_cliente_orden`: una OC no puede tener dos facturas de cliente."""
    db.add(
        FacturaCliente(
            factura_id=uuid.uuid4(),
            numero_factura="F-0002",
            orden_id=datos["orden_id"],  # misma OC que la factura ya sembrada
            empresa_facturadora_id=datos["empresa_id"],
            anunciante_id=datos["anunciante_id"],
            razon_social_facturacion="Otra",
            rfc_facturacion="AGU900101AB1",
            descripcion_factura="Duplicada",
            fecha_inicio_transmision=date(2026, 2, 1),
            fecha_fin_transmision=date(2026, 2, 28),
            fecha_factura=date(2026, 3, 5),
            subtotal_factura=Decimal("100.00"),
            iva_factura=Decimal("16.00"),
            total_factura=Decimal("116.00"),
            cuenta_contable_id=datos["cuenta_id"],
            metodo_pago_clave="PUE",
            created_by=ADMIN_ID,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_factura_agencia_si_admite_varias_por_orden(
    db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """A diferencia de FacturaCliente, la relación con la OC es 1:N (spec)."""
    db.add(
        FacturaAgencia(
            factura_agencia_id=uuid.uuid4(),
            agencia_id=datos["agencia_id"],
            orden_id=datos["orden_id"],  # misma OC: debe permitirse
            fecha_factura_agencia=date(2026, 4, 1),
            monto_factura_agencia=Decimal("500.00"),
            iva_factura_agencia=Decimal("80.00"),
            total_factura_agencia=Decimal("580.00"),
            created_by=ADMIN_ID,
        )
    )
    db.commit()
    assert (
        db.query(FacturaAgencia).filter(FacturaAgencia.orden_id == datos["orden_id"]).count() == 2
    )


def test_no_se_asigna_dos_veces_la_misma_oe_a_la_misma_factura(
    db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """`uq_factura_afiliado_orden_factura_oe`: el reparto sería ambiguo."""
    db.add(
        FacturaAfiliadoOrden(
            id=uuid.uuid4(),
            factura_afiliado_id=datos["factura_afiliado_id"],
            orden_estacion_id=datos["oe_id"],
            monto_asignado=Decimal("1.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_la_misma_oe_si_puede_repartirse_entre_facturas_distintas(
    db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """La UNIQUE es compuesta: no bloquea las parcialidades de emisoras distintas."""
    otra = uuid.uuid4()
    db.add(
        FacturaAfiliado(
            factura_afiliado_id=otra,
            afiliado_id=datos["afiliado_id"],
            factura_emisora="AF-78",
            fecha_factura_afiliado=date(2026, 4, 2),
            monto_factura_afiliado=Decimal("100.00"),
            iva_factura_afiliado=Decimal("16.00"),
            total_factura_afiliado=Decimal("116.00"),
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    db.add(
        FacturaAfiliadoOrden(
            id=uuid.uuid4(),
            factura_afiliado_id=otra,
            orden_estacion_id=datos["oe_id"],
            monto_asignado=Decimal("100.00"),
        )
    )
    db.commit()
    assert db.query(FacturaAfiliadoOrden).count() == 2


def test_check_de_suma_rechaza_un_total_descuadrado(
    db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """`ck_factura_cliente_total_suma` con ROUND en ambos lados: 1 centavo de diferencia
    SIGUE siendo rechazado (el ROUND neutraliza el ruido de float64 de SQLite, ADR-039,
    no enmascara un descuadre real)."""
    db.add(
        FacturaCliente(
            factura_id=uuid.uuid4(),
            numero_factura="F-0003",
            orden_id=uuid.uuid4(),  # otra OC (no choca con la UNIQUE)
            empresa_facturadora_id=datos["empresa_id"],
            anunciante_id=datos["anunciante_id"],
            razon_social_facturacion="X",
            rfc_facturacion="AGU900101AB1",
            descripcion_factura="Descuadrada",
            fecha_inicio_transmision=date(2026, 2, 1),
            fecha_fin_transmision=date(2026, 2, 28),
            fecha_factura=date(2026, 3, 5),
            subtotal_factura=Decimal("100.00"),
            iva_factura=Decimal("16.00"),
            total_factura=Decimal("116.01"),  # 1 centavo de más
            cuenta_contable_id=datos["cuenta_id"],
            metodo_pago_clave="PUE",
            created_by=ADMIN_ID,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_check_del_iva_rechaza_una_tasa_distinta_del_16(
    db: Session, datos: dict[str, uuid.UUID]
) -> None:
    """`ck_factura_cliente_iva_calculado`: el IVA de la factura al cliente es derivado."""
    db.add(
        FacturaCliente(
            factura_id=uuid.uuid4(),
            numero_factura="F-0004",
            orden_id=uuid.uuid4(),
            empresa_facturadora_id=datos["empresa_id"],
            anunciante_id=datos["anunciante_id"],
            razon_social_facturacion="X",
            rfc_facturacion="AGU900101AB1",
            descripcion_factura="IVA al 8%",
            fecha_inicio_transmision=date(2026, 2, 1),
            fecha_fin_transmision=date(2026, 2, 28),
            fecha_factura=date(2026, 3, 5),
            subtotal_factura=Decimal("100.00"),
            iva_factura=Decimal("8.00"),
            total_factura=Decimal("108.00"),
            cuenta_contable_id=datos["cuenta_id"],
            metodo_pago_clave="PUE",
            created_by=ADMIN_ID,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_periodo_contable_debe_ser_yyyy_mm(db: Session, datos: dict[str, uuid.UUID]) -> None:
    db.add(
        CostoAdicional(
            costo_id=uuid.uuid4(),
            tipo_costo="overhead",
            descripcion_costo="Formato inválido",
            periodo_contable="feb-2026",
            monto_costo=Decimal("10.00"),
            created_by=ADMIN_ID,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ── API de lectura ────────────────────────────────────────────────────────────
def test_listar_facturas_cliente(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get("/api/v1/facturacion/clientes", headers=_hdr("facturacion"))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["numero_factura"] == "F-0001"
    assert cuerpo["items"][0]["total_factura"] == "11600.00"


def test_filtrar_facturas_cliente_por_estado(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/facturacion/clientes",
        params={"estado_facturacion": "timbrada"},
        headers=_hdr("facturacion"),
    )
    assert r.json()["total"] == 0
    r = client.get(
        "/api/v1/facturacion/clientes",
        params={"estado_facturacion": "preparada"},
        headers=_hdr("facturacion"),
    )
    assert r.json()["total"] == 1


def test_obtener_factura_cliente_y_404(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(
        f"/api/v1/facturacion/clientes/{datos['factura_id']}", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    assert r.json()["metodo_pago_clave"] == "PUE"
    r = client.get(f"/api/v1/facturacion/clientes/{uuid.uuid4()}", headers=_hdr("facturacion"))
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "no_encontrado"


def test_listar_facturas_afiliado_y_sus_asignaciones(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get("/api/v1/facturacion/afiliados", headers=_hdr("cxp"))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    r = client.get(
        f"/api/v1/facturacion/afiliados/{datos['factura_afiliado_id']}/ordenes",
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200
    asignaciones = r.json()
    assert len(asignaciones) == 1
    assert asignaciones[0]["orden_estacion_id"] == str(datos["oe_id"])
    assert asignaciones[0]["monto_asignado"] == "7000.00"


def test_listar_facturas_agencia_filtrando_por_orden(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/facturacion/agencias",
        params={"orden_id": str(datos["orden_id"])},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["comision_agencia"] == "1160.00"


def test_listar_costos_adicionales_por_periodo(
    client: TestClient, datos: dict[str, uuid.UUID]
) -> None:
    r = client.get(
        "/api/v1/facturacion/costos",
        params={"periodo_contable": "2026-02"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["orden_id"] is None  # costo general, sin OC


def test_busqueda_por_texto(client: TestClient, datos: dict[str, uuid.UUID]) -> None:
    r = client.get(
        "/api/v1/facturacion/clientes", params={"q": "F-000"}, headers=_hdr("facturacion")
    )
    assert r.json()["total"] == 1
    r = client.get(
        "/api/v1/facturacion/clientes", params={"q": "inexistente"}, headers=_hdr("facturacion")
    )
    assert r.json()["total"] == 0


# ── RBAC: dos claves de módulo (ficha de F2) ──────────────────────────────────
@pytest.mark.parametrize(
    "area", ["facturacion", "ventas", "tesoreria", "cxc", "cxp", "direccion", "nominas", "admin"]
)
def test_todas_las_areas_leen_facturas_cliente(
    client: TestClient, datos: dict[str, uuid.UUID], area: str
) -> None:
    """La ficha da lectura de FacturaCliente a todas las áreas; Admin por ADR-040."""
    r = client.get("/api/v1/facturacion/clientes", headers=_hdr(area))
    assert r.status_code == 200, area


@pytest.mark.parametrize(
    "area", ["cxp", "facturacion", "ventas", "tesoreria", "cxc", "direccion", "nominas", "admin"]
)
def test_todas_las_areas_leen_costos(
    client: TestClient, datos: dict[str, uuid.UUID], area: str
) -> None:
    r = client.get("/api/v1/facturacion/afiliados", headers=_hdr(area))
    assert r.status_code == 200, area


def test_un_area_desconocida_no_tiene_acceso(client: TestClient) -> None:
    r = client.get("/api/v1/facturacion/clientes", headers=_hdr("marketing"))
    assert r.status_code in (401, 403, 422)
