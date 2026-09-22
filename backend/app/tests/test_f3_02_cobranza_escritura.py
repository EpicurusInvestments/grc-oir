"""Pruebas F3 · Cobranza — el handoff con F2 y el recálculo de `estatus_cobro` (SQLite).

Lo central: **timbrar una FacturaCliente crea automáticamente su CobranzaFactura**, y
**cancelar una factura con pagos ya recibidos se rechaza**. Además: el recálculo de
`estatus_cobro`/`fecha_cobro` al crear/borrar un `PagoCliente`, la cascada completa
`CobranzaFactura → FacturaCliente → OrdenCliente` cuando el cobro se completa, el
guardarraíl que impide "des-cobrar" borrando un pago, el badge `vencida` y el RBAC.
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
from app.modules.cobranza.cobranza_factura import CobranzaFactura, EstatusCobro, PagoCliente
from app.modules.cobranza.router import router as cobranza_router
from app.modules.facturacion.factura_cliente import EstadoFacturacion, FacturaCliente
from app.modules.facturacion.router import router as facturacion_router
from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente
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
    agencia_id, cuenta_id = uuid.uuid4(), uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=agencia_id,
            nombre_agencia="Agencia Uno",
            rfc_agencia="AGU900101AB1",
            porcentaje_comision_agencia_default=Decimal("10.00"),
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


def _orden(
    db: Session, cat: dict[str, uuid.UUID], estatus: str, folio: str,
    *, subtotal: Decimal = Decimal("10000.00"),
) -> uuid.UUID:
    orden_id = uuid.uuid4()
    iva = (subtotal * Decimal("0.16")).quantize(Decimal("0.01"))
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
            facturacion_directa_cliente=False,
            fecha_inicio_campania=date(2026, 2, 1),
            fecha_fin_campania=date(2026, 2, 28),
            total_dias_campania=28,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=subtotal,
            iva=iva,
            total=(subtotal + iva).quantize(Decimal("0.01")),
            estatus_orden=estatus,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return orden_id


@pytest.fixture
def cat(db: Session) -> dict[str, uuid.UUID]:
    datos = _catalogos(db)
    db.commit()
    return datos


@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(facturacion_router, prefix="/api/v1")
    app.include_router(cobranza_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def _pago(monto: str, fecha: str = "2026-03-05") -> dict[str, str]:
    return {"fecha_pago_cliente": fecha, "monto_aplicado": monto, "metodo_pago_clave": "PUE"}


def _crear_y_timbrar_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], numero: str = "A-1001"
) -> tuple[str, str, uuid.UUID]:
    """Crea una OC cerrada, la factura, la timbra. Devuelve (factura_id, orden_id como
    str, orden_id como UUID) para las pruebas que necesitan ambas formas."""
    orden_id = _orden(db, cat, "orden_cerrada", f"OC-{numero}")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json={
            "ordenes_ids": [str(orden_id)],
            "numero_factura": numero,
            "descripcion_factura": "Servicios de transmisión",
            "fecha_factura": "2026-03-01",
            "cuenta_contable_id": str(cat["cuenta_id"]),
            "metodo_pago_clave": "PUE",
            "forma_pago_clave": "99",
        },
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    factura_id = r.json()["factura_id"]
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado",
        headers=_hdr("facturacion"),
    )
    r2 = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "F" * 36, "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    assert r2.status_code == 200, r2.text
    return factura_id, str(orden_id), orden_id


# ══════════════════════════════════════════════════════════════════════════════
# El handoff de creación — LA prueba central de F3
# ══════════════════════════════════════════════════════════════════════════════
def test_timbrar_crea_automaticamente_la_cobranza_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)

    r = client.get(
        "/api/v1/cobranza/facturas", params={"factura_id": factura_id}, headers=_hdr("cxc")
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1, "timbrar la factura debió crear su CobranzaFactura"
    cobranza = items[0]
    assert cobranza["factura_id"] == factura_id
    assert cobranza["metodo_pago_clave"] == "PUE"  # heredado de la factura
    assert cobranza["dias_credito"] == 30  # Anunciante.dias_credito_default
    # Ancla provisional: fecha_entrega_factura aún no existe, se usó fecha_timbrado.
    assert cobranza["fecha_estimada_cobro"] == "2026-04-01"  # 2026-03-02 + 30 días
    assert cobranza["estatus_cobro"] == "pendiente"
    assert cobranza["importe_cobrado"] == "0.00"
    assert Decimal(cobranza["importe_pendiente_cobro"]) == Decimal("11600.00")
    assert cobranza["numero_factura"] == "A-1001"


def test_timbrar_es_idempotente_no_duplica_la_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    # Reintentar el timbrado (mismo estado, ya timbrada): no debe crear una segunda.
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "F" * 36, "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    total = (
        db.query(CobranzaFactura)
        .filter(CobranzaFactura.factura_id == uuid.UUID(factura_id))
        .count()
    )
    assert total == 1


def test_entregar_recalcula_fecha_estimada_con_el_ancla_real(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/entregar",
        json={"fecha_entrega_factura": "2026-03-10"},
        headers=_hdr("facturacion"),
    )
    r = client.get(f"/api/v1/cobranza/facturas/{_cobranza_id(db, factura_id)}", headers=_hdr("cxc"))
    assert r.json()["fecha_estimada_cobro"] == "2026-04-09"  # 2026-03-10 + 30


def _cobranza_id(db: Session, factura_id: str) -> str:
    obj = (
        db.query(CobranzaFactura)
        .filter(CobranzaFactura.factura_id == uuid.UUID(factura_id))
        .one()
    )
    return str(obj.cobranza_id)


# ══════════════════════════════════════════════════════════════════════════════
# El handoff de cancelación — LA otra prueba central
# ══════════════════════════════════════════════════════════════════════════════
def test_cancelar_una_factura_con_pagos_recibidos_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id_str, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    r = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("1000.00"),
        headers=_hdr("cxc"),
    )
    assert r.status_code == 201, r.text

    r2 = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion")
    )
    assert r2.status_code == 400
    assert r2.json()["error"]["codigo"] == "error_dominio"

    # Nada se tocó: ni la factura ni la CobranzaFactura ni la orden.
    db.expire_all()
    factura = db.get(FacturaCliente, uuid.UUID(factura_id))
    assert factura.estado_facturacion == EstadoFacturacion.TIMBRADA.value
    quedan = (
        db.query(CobranzaFactura).filter(CobranzaFactura.factura_id == factura.factura_id).count()
    )
    assert quedan == 1
    orden = db.get(OrdenCliente, uuid.UUID(orden_id_str))
    assert orden.estatus_orden == EstatusOrden.FACTURADA.value


def test_cancelar_sin_pagos_borra_la_cobranza_y_revierte_la_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id_str, _ = _crear_y_timbrar_factura(client, db, cat)

    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion")
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.query(CobranzaFactura).filter(
        CobranzaFactura.factura_id == uuid.UUID(factura_id)
    ).count() == 0
    orden = db.get(OrdenCliente, uuid.UUID(orden_id_str))
    assert orden.estatus_orden == EstatusOrden.ORDEN_CERRADA.value


# ══════════════════════════════════════════════════════════════════════════════
# Recálculo de estatus_cobro/fecha_cobro al crear/borrar un PagoCliente
# ══════════════════════════════════════════════════════════════════════════════
def test_pago_parcial_dejar_pendiente_a_cobro_parcial(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)  # total = 11600.00
    cobranza_id = _cobranza_id(db, factura_id)

    r = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=_pago("5000.00"), headers=_hdr("cxc")
    )
    assert r.status_code == 201, r.text

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["estatus_cobro"] == "cobro_parcial"
    assert Decimal(cobranza["importe_cobrado"]) == Decimal("5000.00")
    assert cobranza["fecha_cobro"] is None


def test_pago_completo_completa_la_cascada_hasta_ordencliente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La prueba de la cascada de 3 pasos: CobranzaFactura → FacturaCliente → OrdenCliente."""
    factura_id, orden_id_str, orden_id = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    r = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("11600.00"),
        headers=_hdr("cxc"),
    )
    assert r.status_code == 201, r.text

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["estatus_cobro"] == "cobrada"
    assert cobranza["fecha_cobro"] == date.today().isoformat()

    db.expire_all()
    factura = db.get(FacturaCliente, uuid.UUID(factura_id))
    assert factura.estado_facturacion == EstadoFacturacion.COBRADA.value
    orden = db.get(OrdenCliente, orden_id)
    assert orden.estatus_orden == EstatusOrden.COBRADA.value


def test_borrar_un_pago_que_no_completo_el_cobro_recalcula_sin_problema(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    pago = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=_pago("3000.00"), headers=_hdr("cxc")
    ).json()

    r = client.delete(f"/api/v1/cobranza/pagos/{pago['pago_cliente_id']}", headers=_hdr("cxc"))
    assert r.status_code == 204

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["estatus_cobro"] == "pendiente"
    assert Decimal(cobranza["importe_cobrado"]) == Decimal("0.00")


def test_borrar_un_pago_que_desharia_un_cobro_completo_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El guardarraíl de la cascada sin reversa: una vez `cobrada`, no se puede
    "des-cobrar" borrando el pago que la completó."""
    factura_id, _, orden_id = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    pago = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("11600.00"),
        headers=_hdr("cxc"),
    ).json()

    r = client.delete(f"/api/v1/cobranza/pagos/{pago['pago_cliente_id']}", headers=_hdr("cxc"))
    assert r.status_code == 409, r.text

    # Nada retrocedió: la cascada sigue firme en los 3 niveles.
    db.expire_all()
    cobranza = db.get(CobranzaFactura, uuid.UUID(pago["cobranza_id"]))
    assert cobranza.estatus_cobro == EstatusCobro.COBRADA.value
    factura = db.get(FacturaCliente, uuid.UUID(factura_id))
    assert factura.estado_facturacion == EstadoFacturacion.COBRADA.value
    orden = db.get(OrdenCliente, orden_id)
    assert orden.estatus_orden == EstatusOrden.COBRADA.value
    pago_id = uuid.UUID(pago["pago_cliente_id"])
    assert db.query(PagoCliente).filter(PagoCliente.pago_cliente_id == pago_id).count() == 1


def test_borrar_un_pago_extra_sobre_una_ya_cobrada_si_se_permite(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El guardarraíl es preciso, no un candado ciego: si hay un pago DE MÁS y sigue
    cubierto tras borrar uno, sí se permite (la factura sigue cobrada de todas formas)."""
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)  # total 11600.00
    cobranza_id = _cobranza_id(db, factura_id)

    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("11600.00"),
        headers=_hdr("cxc"),
    )
    pago_extra = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("500.00", fecha="2026-03-06"),
        headers=_hdr("cxc"),
    ).json()

    pago_extra_id = pago_extra["pago_cliente_id"]
    r = client.delete(f"/api/v1/cobranza/pagos/{pago_extra_id}", headers=_hdr("cxc"))
    assert r.status_code == 204, r.text

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["estatus_cobro"] == "cobrada"


# ══════════════════════════════════════════════════════════════════════════════
# Badge `vencida` — derivado, nunca almacenado
# ══════════════════════════════════════════════════════════════════════════════
def test_vencida_es_badge_derivado_no_columna(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    # Fuerza una fecha_estimada_cobro ya vencida, directo en el ORM (el endpoint no la
    # deja capturar: es calculada).
    obj = db.get(CobranzaFactura, uuid.UUID(cobranza_id))
    obj.fecha_estimada_cobro = date(2020, 1, 1)
    db.commit()

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["vencida"] is True
    # El CHECK de la columna solo admite 3 valores — `vencida` nunca aparece ahí.
    assert cobranza["estatus_cobro"] in ("pendiente", "cobro_parcial", "cobrada")


def test_una_factura_cobrada_nunca_esta_vencida_aunque_pase_la_fecha(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)
    obj = db.get(CobranzaFactura, uuid.UUID(cobranza_id))
    obj.fecha_estimada_cobro = date(2020, 1, 1)
    db.commit()

    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("11600.00"),
        headers=_hdr("cxc"),
    )
    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["vencida"] is False


# ══════════════════════════════════════════════════════════════════════════════
# RBAC (matriz de la ficha)
# ══════════════════════════════════════════════════════════════════════════════
def test_rbac_cxc_captura_ventas_solo_lee(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    assert client.get(
        "/api/v1/cobranza/facturas", headers=_hdr("ventas")
    ).status_code == 200
    pago = {
        "fecha_pago_cliente": "2026-03-05",
        "monto_aplicado": "100.00",
        "metodo_pago_clave": "PUE",
    }
    r_bloqueado = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=pago, headers=_hdr("ventas")
    )
    assert r_bloqueado.status_code == 403

    r_permitido = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=pago, headers=_hdr("cxc")
    )
    assert r_permitido.status_code == 201


def test_rbac_nominas_sin_acceso_a_pagos_pero_si_a_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La matriz de la ficha SÍ le da lectura de cobranza a Nóminas; no la excluye."""
    assert client.get("/api/v1/cobranza/facturas", headers=_hdr("nominas")).status_code == 200
