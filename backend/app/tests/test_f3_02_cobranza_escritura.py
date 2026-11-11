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
    *, subtotal: Decimal = Decimal("10000.00"), directa: bool = False,
    con_agencia_referencia: bool = False,
) -> uuid.UUID:
    """`directa=True` (ADR-235): orden facturada DIRECTO al anunciante — por default
    sigue siendo vía agencia (comportamiento histórico de este archivo).

    `con_agencia_referencia=True` (ADR-236, solo tiene efecto con `directa=True`): la
    orden de todos modos trae `agencia_id` capturado como REFERENCIA — el caso real del
    bug reportado, donde `agencia_id IS NULL` NO bastaba para detectar "es directa"."""
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
            agencia_id=cat["agencia_id"] if (not directa or con_agencia_referencia) else None,
            facturacion_directa_cliente=directa,
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


def _pago(monto: str, cat: dict[str, uuid.UUID], fecha: str = "2026-03-05") -> dict[str, object]:
    # ADR-225: forma_pago_clave/cuenta_contable_id pasan a ser obligatorios.
    return {
        "fecha_pago_cliente": fecha,
        "monto_aplicado": monto,
        "metodo_pago_clave": "PUE",
        "forma_pago_clave": "99",
        "cuenta_contable_id": str(cat["cuenta_id"]),
    }


def _crear_y_timbrar_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], numero: str = "A-1001",
    *, directa: bool = False, con_agencia_referencia: bool = False,
) -> tuple[str, str, uuid.UUID]:
    """Crea una OC cerrada, la factura, la timbra. Devuelve (factura_id, orden_id como
    str, orden_id como UUID) para las pruebas que necesitan ambas formas."""
    orden_id = _orden(
        db, cat, "orden_cerrada", f"OC-{numero}",
        directa=directa, con_agencia_referencia=con_agencia_referencia,
    )
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
            # ADR-223: obligatorias desde `FacturaClienteCreate` — este helper no las
            # traía (bug preexistente, ajeno a F3, descubierto al tocar este archivo).
            "clave_prod_serv": "82101601",
            "clave_unidad": "E48",
            "moneda_sat": "MXN",
            "tipo_comprobante": "I",
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
        json=_pago("1000.00", cat),
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
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("5000.00", cat),
        headers=_hdr("cxc"),
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
        json=_pago("11600.00", cat),
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
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("3000.00", cat),
        headers=_hdr("cxc"),
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
        json=_pago("11600.00", cat),
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
        json=_pago("11600.00", cat),
        headers=_hdr("cxc"),
    )
    pago_extra = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("500.00", cat, fecha="2026-03-06"),
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
        json=_pago("11600.00", cat),
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
        "forma_pago_clave": "99",
        "cuenta_contable_id": str(cat["cuenta_id"]),
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


# ══════════════════════════════════════════════════════════════════════════════
# ADR-225 (petición del usuario): Pago Múltiple para varias facturas
# ══════════════════════════════════════════════════════════════════════════════


def _pago_multiple(cat: dict[str, uuid.UUID], pagos: list[dict[str, str]]) -> dict[str, object]:
    return {
        "fecha_pago_cliente": "2026-03-10",
        "monto_total_pago": "20000.00",
        "forma_pago_clave": "03",
        "cuenta_contable_id": str(cat["cuenta_id"]),
        "pagos": pagos,
    }


def test_agencia_id_se_deriva_de_la_factura_al_crear_la_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """`_orden()` (este archivo) factura siempre vía agencia (`agencia_id=cat["agencia_
    id"]`, `facturacion_directa_cliente=False`) — mismo criterio que `anunciante_id`,
    ya cubierto por el resto de la suite."""
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)
    r = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r.json()["agencia_id"] == str(cat["agencia_id"])


def test_filtro_por_agencia_id_en_el_listado(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _crear_y_timbrar_factura(client, db, cat, "A-2001")
    r = client.get(
        "/api/v1/cobranza/facturas",
        params={"agencia_id": str(cat["agencia_id"])},
        headers=_hdr("cxc"),
    )
    assert r.json()["total"] >= 1
    otra_agencia = uuid.uuid4()
    r_otra = client.get(
        "/api/v1/cobranza/facturas", params={"agencia_id": str(otra_agencia)}, headers=_hdr("cxc")
    )
    assert r_otra.json()["total"] == 0


def test_filtro_por_anunciante_id_excluye_facturas_de_su_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """ADR-235 (petición del usuario, reportado con captura): "Pago Múltiple del
    Anunciante" (filtro `anunciante_id` solo) NO debe traer las facturas de ESE MISMO
    anunciante que en realidad se facturaron a su agencia — `anunciante_id` nunca es
    NULL (es "el anunciante de la orden", no "a quién se factura")."""
    _crear_y_timbrar_factura(client, db, cat, "A-2050", directa=True)
    _crear_y_timbrar_factura(client, db, cat, "A-2051")  # vía agencia (default del archivo)

    r = client.get(
        "/api/v1/cobranza/facturas",
        params={"anunciante_id": str(cat["anunciante_id"])},
        headers=_hdr("cxc"),
    )
    items = r.json()["items"]
    assert r.json()["total"] == 1, "no debió incluir la facturada a la agencia"
    assert items[0]["numero_factura"] == "A-2050"
    assert items[0]["agencia_id"] is None


def test_filtro_por_agencia_id_no_se_ve_afectado_por_anunciante_id(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Caso simple (orden directa SIN ninguna agencia capturada) — el caso con agencia
    capturada COMO REFERENCIA (el bug real) está en
    `test_agencia_capturada_como_referencia_no_cuenta_como_facturada_a_la_agencia`."""
    _crear_y_timbrar_factura(client, db, cat, "A-2060", directa=True)
    _crear_y_timbrar_factura(client, db, cat, "A-2061")  # vía agencia

    r = client.get(
        "/api/v1/cobranza/facturas",
        params={"agencia_id": str(cat["agencia_id"])},
        headers=_hdr("cxc"),
    )
    items = r.json()["items"]
    assert r.json()["total"] == 1, "no debió incluir la facturada directo al anunciante"
    assert items[0]["numero_factura"] == "A-2061"


def test_agencia_capturada_como_referencia_no_cuenta_como_facturada_a_la_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """ADR-236 (petición del usuario, reportado con captura) — el bug REAL: una orden
    `facturacion_directa_cliente=True` que de todos modos trae `agencia_id` capturado
    como referencia. `agencia_id IS NULL` (ADR-235) NO detectaba esto — la factura
    seguía apareciendo en el modo "de la Agencia" Y desaparecía del modo "del
    Anunciante". `facturado_directo` (copiado de `FacturaCliente`, calculado igual que
    `_receptor_de()`) sí lo distingue."""
    _crear_y_timbrar_factura(
        client, db, cat, "A-2070", directa=True, con_agencia_referencia=True
    )
    _crear_y_timbrar_factura(client, db, cat, "A-2071")  # vía agencia, de verdad

    r_agencia = client.get(
        "/api/v1/cobranza/facturas",
        params={"agencia_id": str(cat["agencia_id"])},
        headers=_hdr("cxc"),
    )
    assert r_agencia.json()["total"] == 1, "no debió incluir la directa con agencia de referencia"
    assert r_agencia.json()["items"][0]["numero_factura"] == "A-2071"

    r_anunciante = client.get(
        "/api/v1/cobranza/facturas",
        params={"anunciante_id": str(cat["anunciante_id"])},
        headers=_hdr("cxc"),
    )
    assert r_anunciante.json()["total"] == 1, "la directa con agencia de referencia debe salir aquí"
    assert r_anunciante.json()["items"][0]["numero_factura"] == "A-2070"


def test_pago_individual_guarda_las_claves_nuevas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2002")
    cobranza_id = _cobranza_id(db, factura_id)
    payload = _pago("11600.00", cat)
    payload["fecha_deposito"] = "2026-03-06"
    payload["numero_pago"] = "1 de 1"
    r = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=payload, headers=_hdr("cxc")
    )
    assert r.status_code == 201, r.text
    leido = r.json()
    assert leido["forma_pago_clave"] == "99"
    assert leido["fecha_deposito"] == "2026-03-06"
    assert leido["numero_pago"] == "1 de 1"
    assert leido["cuenta_contable_id"] == str(cat["cuenta_id"])
    assert leido["pago_multiple_id"] is None


def test_pago_multiple_registra_un_pago_por_factura_con_el_mismo_lote(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """2 facturas del MISMO anunciante/agencia (`cat`, siempre el mismo en este
    archivo) — un solo pago múltiple las cubre, cada una con su propio monto, todas
    con el mismo `pago_multiple_id`."""
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2010")
    factura_2, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2011")
    cobranza_1 = _cobranza_id(db, factura_1)
    cobranza_2 = _cobranza_id(db, factura_2)

    payload = _pago_multiple(
        cat,
        [
            {"cobranza_id": cobranza_1, "monto_aplicado": "11600.00"},
            {"cobranza_id": cobranza_2, "monto_aplicado": "5000.00"},
        ],
    )
    payload["monto_total_pago"] = "16600.00"  # exacto: sin sobrante (ver ADR-230 aparte)
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text
    creados = r.json()
    assert len(creados) == 2
    assert creados[0]["pago_multiple_id"] == creados[1]["pago_multiple_id"]
    assert creados[0]["pago_multiple_id"] is not None

    # Factura 1 cubierta por completo -> cobrada; factura 2 solo parcial.
    c1 = client.get(f"/api/v1/cobranza/facturas/{cobranza_1}", headers=_hdr("cxc")).json()
    c2 = client.get(f"/api/v1/cobranza/facturas/{cobranza_2}", headers=_hdr("cxc")).json()
    assert c1["estatus_cobro"] == "cobrada"
    assert c2["estatus_cobro"] == "cobro_parcial"
    assert c2["importe_cobrado"] == "5000.00"


# ADR-256 (petición del usuario, "NEW FEATURE"): "Pagado en sistema externo" — mismo
# criterio que ADR-248 (facturado_en_sistema_externo), solo identifica el pago.
def test_pago_individual_acepta_pagado_en_sistema_externo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat)
    cobranza_id = _cobranza_id(db, factura_id)

    pago = _pago("1000.00", cat)
    pago["pagado_en_sistema_externo"] = True
    r = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=pago, headers=_hdr("cxc")
    )
    assert r.status_code == 201, r.text
    assert r.json()["pagado_en_sistema_externo"] is True

    r_sin_marcar = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=_pago("500.00", cat),
        headers=_hdr("cxc"),
    )
    assert r_sin_marcar.status_code == 201, r_sin_marcar.text
    assert r_sin_marcar.json()["pagado_en_sistema_externo"] is False


def test_pago_multiple_acepta_pagado_en_sistema_externo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2012")
    cobranza_1 = _cobranza_id(db, factura_1)

    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "11600.00"}])
    payload["monto_total_pago"] = "11600.00"
    payload["pagado_en_sistema_externo"] = True
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text
    assert r.json()[0]["pagado_en_sistema_externo"] is True


def test_pago_multiple_rechaza_si_la_suma_excede_el_monto_total(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2020")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "11600.00"}])
    payload["monto_total_pago"] = "5000.00"  # menor a lo asignado
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 400
    # Nada debió quedar guardado.
    c1 = client.get(f"/api/v1/cobranza/facturas/{cobranza_1}", headers=_hdr("cxc")).json()
    assert c1["estatus_cobro"] == "pendiente"


def test_pago_multiple_rechaza_factura_repetida_en_el_mismo_lote(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2030")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(
        cat,
        [
            {"cobranza_id": cobranza_1, "monto_aplicado": "1000.00"},
            {"cobranza_id": cobranza_1, "monto_aplicado": "2000.00"},
        ],
    )
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 400


def test_pago_multiple_no_guarda_nada_si_una_factura_del_lote_no_existe(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Atómico: si la 2a factura del lote no existe, la 1a tampoco debe quedar
    guardada (todo o nada, misma transacción)."""
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2040")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(
        cat,
        [
            {"cobranza_id": cobranza_1, "monto_aplicado": "1000.00"},
            {"cobranza_id": str(uuid.uuid4()), "monto_aplicado": "500.00"},
        ],
    )
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 404
    c1 = client.get(f"/api/v1/cobranza/facturas/{cobranza_1}", headers=_hdr("cxc")).json()
    assert c1["estatus_cobro"] == "pendiente"
    assert c1["importe_cobrado"] == "0.00"


def test_pago_multiple_exige_cuenta_contable_valida(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2050")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "1000.00"}])
    payload["cuenta_contable_id"] = str(uuid.uuid4())
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 400


def test_rbac_pago_multiple_exige_cobranza_crear(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2060")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "1000.00"}])
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("ventas"))
    assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# "Número de parcialidad" (petición del usuario): calculado = numero_pago del ÚLTIMO
# PagoCliente de la cobranza.
# ══════════════════════════════════════════════════════════════════════════════
def test_ultimo_numero_pago_es_null_sin_pagos(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2070")
    cobranza_id = _cobranza_id(db, factura_id)
    r = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r.json()["ultimo_numero_pago"] is None


def test_ultimo_numero_pago_toma_el_de_fecha_mas_reciente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2071")
    cobranza_id = _cobranza_id(db, factura_id)

    pago1 = _pago("3000.00", cat, fecha="2026-03-05")
    pago1["numero_pago"] = "1 de 3"
    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=pago1, headers=_hdr("cxc")
    )

    # Se captura DESPUÉS pero con fecha de pago ANTERIOR: no debe desplazar al de arriba.
    pago_fuera_de_orden = _pago("1000.00", cat, fecha="2026-03-01")
    pago_fuera_de_orden["numero_pago"] = "0 de 3"
    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=pago_fuera_de_orden,
        headers=_hdr("cxc"),
    )

    r = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r.json()["ultimo_numero_pago"] == "1 de 3"

    pago2 = _pago("2000.00", cat, fecha="2026-03-10")
    pago2["numero_pago"] = "2 de 3"
    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=pago2, headers=_hdr("cxc")
    )

    r2 = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r2.json()["ultimo_numero_pago"] == "2 de 3"


def test_ultimo_numero_pago_tambien_lo_alimenta_el_pago_multiple(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2072")
    cobranza_1 = _cobranza_id(db, factura_1)
    # ADR-227: `numero_pago` vive POR RENGLÓN, no a nivel del pago múltiple completo.
    payload = _pago_multiple(
        cat,
        [{"cobranza_id": cobranza_1, "monto_aplicado": "1000.00", "numero_pago": "1 de 1"}],
    )
    r0 = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r0.status_code == 201, r0.text

    r = client.get(f"/api/v1/cobranza/facturas/{cobranza_1}", headers=_hdr("cxc"))
    assert r.json()["ultimo_numero_pago"] == "1 de 1"


# ══════════════════════════════════════════════════════════════════════════════
# ADR-227 (petición del usuario): "Número de Parcialidad" calculada en la tabla de
# Pago Múltiple + tope de monto por renglón contra el pendiente (solo frontend).
# ══════════════════════════════════════════════════════════════════════════════
def test_siguiente_numero_pago_es_1_sin_pagos(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2080")
    cobranza_id = _cobranza_id(db, factura_id)
    r = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r.json()["siguiente_numero_pago"] == "1"


def test_siguiente_numero_pago_cuenta_los_pagos_ya_registrados(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2081")
    cobranza_id = _cobranza_id(db, factura_id)

    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=_pago("1000.00", cat),
        headers=_hdr("cxc"),
    )
    r1 = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r1.json()["siguiente_numero_pago"] == "2"

    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos",
        json=_pago("1000.00", cat, fecha="2026-03-06"),
        headers=_hdr("cxc"),
    )
    r2 = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc"))
    assert r2.json()["siguiente_numero_pago"] == "3"


def test_pago_multiple_guarda_numero_pago_distinto_por_renglon(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Dos facturas en el MISMO lote, cada una con su propia parcialidad — una no
    desplaza a la otra (ADR-227: `numero_pago` vive por renglón, no a nivel de lote)."""
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2082")
    factura_2, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2083")
    cobranza_1 = _cobranza_id(db, factura_1)
    cobranza_2 = _cobranza_id(db, factura_2)
    # factura_2 ya trae un pago previo: su "siguiente" debe ser "2", no "1".
    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_2}/pagos", json=_pago("500.00", cat),
        headers=_hdr("cxc"),
    )

    payload = _pago_multiple(
        cat,
        [
            {"cobranza_id": cobranza_1, "monto_aplicado": "1000.00", "numero_pago": "1"},
            {"cobranza_id": cobranza_2, "monto_aplicado": "2000.00", "numero_pago": "2"},
        ],
    )
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text

    c1 = client.get(f"/api/v1/cobranza/facturas/{cobranza_1}", headers=_hdr("cxc")).json()
    c2 = client.get(f"/api/v1/cobranza/facturas/{cobranza_2}", headers=_hdr("cxc")).json()
    assert c1["ultimo_numero_pago"] == "1"
    assert c2["ultimo_numero_pago"] == "2"


def test_pago_multiple_rechaza_numero_pago_top_level_ya_no_existe(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """ADR-227: `numero_pago` a nivel del pago múltiple completo ya no es un campo
    válido (se movió por renglón) — mandarlo ahí se rechaza (`extra="forbid"`)."""
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2084")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "1000.00"}])
    payload["numero_pago"] = "1 de 1"
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# ADR-229 (petición del usuario): "Pagos no asignados" — capturar un pago sin
# elegir factura todavía, y asignarla después.
# ══════════════════════════════════════════════════════════════════════════════
def test_crear_pago_sin_asignar_no_pide_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    payload = _pago("1500.00", cat)
    r = client.post("/api/v1/cobranza/pagos/no-asignados", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text
    leido = r.json()
    assert leido["cobranza_id"] is None
    assert leido["monto_aplicado"] == "1500.00"


def test_listar_no_asignados_solo_trae_los_sin_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2090")
    cobranza_id = _cobranza_id(db, factura_id)
    client.post(
        f"/api/v1/cobranza/facturas/{cobranza_id}/pagos", json=_pago("1000.00", cat),
        headers=_hdr("cxc"),
    )
    client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("2000.00", cat), headers=_hdr("cxc")
    )

    r = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["monto_aplicado"] == "2000.00"
    assert items[0]["cobranza_id"] is None


def test_asignar_un_pago_no_asignado_recalcula_la_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2091")  # total 11600.00
    cobranza_id = _cobranza_id(db, factura_id)

    pago = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("11600.00", cat), headers=_hdr("cxc")
    ).json()

    r = client.post(
        f"/api/v1/cobranza/pagos/{pago['pago_cliente_id']}/asignar",
        json={"cobranza_id": cobranza_id, "monto_aplicado": "11600.00"},
        headers=_hdr("cxc"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["cobranza_id"] == cobranza_id

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["estatus_cobro"] == "cobrada"
    assert cobranza["importe_cobrado"] == "11600.00"


def test_asignar_un_pago_ya_asignado_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2092")
    factura_2, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2093")
    cobranza_1 = _cobranza_id(db, factura_1)
    cobranza_2 = _cobranza_id(db, factura_2)

    pago = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_1}/pagos", json=_pago("1000.00", cat),
        headers=_hdr("cxc"),
    ).json()

    r = client.post(
        f"/api/v1/cobranza/pagos/{pago['pago_cliente_id']}/asignar",
        json={"cobranza_id": cobranza_2, "monto_aplicado": "1000.00"},
        headers=_hdr("cxc"),
    )
    assert r.status_code == 409


def test_asignar_a_una_cobranza_inexistente_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    pago = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("1000.00", cat), headers=_hdr("cxc")
    ).json()
    r = client.post(
        f"/api/v1/cobranza/pagos/{pago['pago_cliente_id']}/asignar",
        json={"cobranza_id": str(uuid.uuid4()), "monto_aplicado": "1000.00"},
        headers=_hdr("cxc"),
    )
    assert r.status_code == 404


def test_borrar_un_pago_no_asignado_no_necesita_cobranza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    pago = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("1000.00", cat), headers=_hdr("cxc")
    ).json()
    r = client.delete(f"/api/v1/cobranza/pagos/{pago['pago_cliente_id']}", headers=_hdr("cxc"))
    assert r.status_code == 204

    r2 = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    assert r2.json()["total"] == 0


def test_rbac_pago_no_asignado_exige_cobranza_crear(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    payload = _pago("1000.00", cat)
    r = client.post("/api/v1/cobranza/pagos/no-asignados", json=payload, headers=_hdr("ventas"))
    assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# ADR-230 (petición del usuario): "pago de menos" en Pago Múltiple genera un huérfano
# con el sobrante, y ese huérfano se puede repartir después con la misma
# funcionalidad (pago_origen_id).
# ══════════════════════════════════════════════════════════════════════════════
def test_pago_de_menos_genera_un_huerfano_con_el_sobrante(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2100")  # total 11600.00
    cobranza_1 = _cobranza_id(db, factura_1)

    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "5000.00"}])
    payload["monto_total_pago"] = "8000.00"  # sobran 3000.00
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text
    creados = r.json()
    assert len(creados) == 2
    huerfano = next(p for p in creados if p["cobranza_id"] is None)
    asignado = next(p for p in creados if p["cobranza_id"] is not None)
    assert huerfano["monto_aplicado"] == "3000.00"
    assert asignado["monto_aplicado"] == "5000.00"
    assert huerfano["pago_multiple_id"] == asignado["pago_multiple_id"]

    r2 = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["pago_cliente_id"] == huerfano["pago_cliente_id"]


def test_pago_exacto_no_genera_huerfano(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2101")
    cobranza_1 = _cobranza_id(db, factura_1)
    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_1, "monto_aplicado": "5000.00"}])
    payload["monto_total_pago"] = "5000.00"
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text
    assert len(r.json()) == 1


def test_repartir_un_huerfano_lo_borra_y_crea_los_nuevos_pagos(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El huérfano se reparte entre 2 facturas distintas y desaparece (se borra), sin
    dejar sobrante esta vez (repartido por completo)."""
    factura_a, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2102")
    factura_b, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2103")
    cobranza_a = _cobranza_id(db, factura_a)
    cobranza_b = _cobranza_id(db, factura_b)

    huerfano = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("3000.00", cat), headers=_hdr("cxc")
    ).json()

    payload = _pago_multiple(
        cat,
        [
            {"cobranza_id": cobranza_a, "monto_aplicado": "1000.00"},
            {"cobranza_id": cobranza_b, "monto_aplicado": "2000.00"},
        ],
    )
    payload["monto_total_pago"] = "3000.00"
    payload["pago_origen_id"] = huerfano["pago_cliente_id"]
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text
    assert len(r.json()) == 2  # sin sobrante: el huérfano original no sobrevive

    # El huérfano original ya no existe.
    r_no_asignados = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    assert r_no_asignados.json()["total"] == 0

    ca = client.get(f"/api/v1/cobranza/facturas/{cobranza_a}", headers=_hdr("cxc")).json()
    cb = client.get(f"/api/v1/cobranza/facturas/{cobranza_b}", headers=_hdr("cxc")).json()
    assert ca["importe_cobrado"] == "1000.00"
    assert cb["importe_cobrado"] == "2000.00"


def test_repartir_un_huerfano_parcialmente_deja_un_huerfano_nuevo_mas_chico(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_a, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2104")
    cobranza_a = _cobranza_id(db, factura_a)
    huerfano = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("3000.00", cat), headers=_hdr("cxc")
    ).json()

    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_a, "monto_aplicado": "1000.00"}])
    payload["monto_total_pago"] = "3000.00"
    payload["pago_origen_id"] = huerfano["pago_cliente_id"]
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 201, r.text

    r_no_asignados = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    items = r_no_asignados.json()["items"]
    assert len(items) == 1
    assert items[0]["pago_cliente_id"] != huerfano["pago_cliente_id"]  # es uno NUEVO
    assert items[0]["monto_aplicado"] == "2000.00"


def test_repartir_un_pago_ya_asignado_como_si_fuera_huerfano_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_a, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2105")
    factura_b, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2106")
    cobranza_a = _cobranza_id(db, factura_a)
    cobranza_b = _cobranza_id(db, factura_b)

    ya_asignado = client.post(
        f"/api/v1/cobranza/facturas/{cobranza_a}/pagos", json=_pago("1000.00", cat),
        headers=_hdr("cxc"),
    ).json()

    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_b, "monto_aplicado": "1000.00"}])
    payload["monto_total_pago"] = "1000.00"
    payload["pago_origen_id"] = ya_asignado["pago_cliente_id"]
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 409


def test_repartir_un_pago_origen_inexistente_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_a, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2107")
    cobranza_a = _cobranza_id(db, factura_a)
    payload = _pago_multiple(cat, [{"cobranza_id": cobranza_a, "monto_aplicado": "1000.00"}])
    payload["monto_total_pago"] = "1000.00"
    payload["pago_origen_id"] = str(uuid.uuid4())
    r = client.post("/api/v1/cobranza/pagos/multiples", json=payload, headers=_hdr("cxc"))
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# ADR-231 (petición del usuario): "Asignar" (ADR-229) con monto PARCIAL — no debe
# asignarle de más a la factura que el usuario eligió; el resto se queda como un
# huérfano más chico (mismo id).
# ══════════════════════════════════════════════════════════════════════════════
def test_asignar_parcial_deja_el_mismo_huerfano_mas_chico(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2110")
    cobranza_id = _cobranza_id(db, factura_id)  # pendiente 11600.00

    huerfano = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("1000.00", cat), headers=_hdr("cxc")
    ).json()

    r = client.post(
        f"/api/v1/cobranza/pagos/{huerfano['pago_cliente_id']}/asignar",
        json={"cobranza_id": cobranza_id, "monto_aplicado": "486.40"},
        headers=_hdr("cxc"),
    )
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["pago_cliente_id"] != huerfano["pago_cliente_id"]  # es uno NUEVO
    assert nuevo["cobranza_id"] == cobranza_id
    assert nuevo["monto_aplicado"] == "486.40"

    cobranza = client.get(f"/api/v1/cobranza/facturas/{cobranza_id}", headers=_hdr("cxc")).json()
    assert cobranza["estatus_cobro"] == "cobro_parcial"
    assert cobranza["importe_cobrado"] == "486.40"

    # El huérfano ORIGINAL sigue existiendo, ahora con el restante.
    r_no_asignados = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    items = r_no_asignados.json()["items"]
    assert len(items) == 1
    assert items[0]["pago_cliente_id"] == huerfano["pago_cliente_id"]
    assert items[0]["monto_aplicado"] == "513.60"


def test_asignar_el_monto_completo_no_hace_split_reusa_la_misma_fila(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2111")
    cobranza_id = _cobranza_id(db, factura_id)
    huerfano = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("1000.00", cat), headers=_hdr("cxc")
    ).json()

    r = client.post(
        f"/api/v1/cobranza/pagos/{huerfano['pago_cliente_id']}/asignar",
        json={"cobranza_id": cobranza_id, "monto_aplicado": "1000.00"},
        headers=_hdr("cxc"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pago_cliente_id"] == huerfano["pago_cliente_id"]  # MISMA fila

    r_no_asignados = client.get("/api/v1/cobranza/pagos/no-asignados", headers=_hdr("cxc"))
    assert r_no_asignados.json()["total"] == 0


def test_asignar_mas_del_monto_del_huerfano_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _, _ = _crear_y_timbrar_factura(client, db, cat, "A-2112")
    cobranza_id = _cobranza_id(db, factura_id)
    huerfano = client.post(
        "/api/v1/cobranza/pagos/no-asignados", json=_pago("1000.00", cat), headers=_hdr("cxc")
    ).json()

    r = client.post(
        f"/api/v1/cobranza/pagos/{huerfano['pago_cliente_id']}/asignar",
        json={"cobranza_id": cobranza_id, "monto_aplicado": "1000.01"},
        headers=_hdr("cxc"),
    )
    assert r.status_code == 400
