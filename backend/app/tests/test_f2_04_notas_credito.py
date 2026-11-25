"""Pruebas F2 · Notas de Crédito (petición del usuario, con captura) — SQLite.

`FacturaCliente` con `tipo_comprobante == "E"`: sin órdenes propias (receptor/empresa/
forma de pago heredados de la factura de ORIGEN), montos NEGADOS al persistir, folio
`NC-AAAA-MM-folio`. Al timbrarse, se aplica como un `PagoCliente` SINTÉTICO sobre la
`CobranzaFactura` de la factura de origen (nunca crea una propia) — reutiliza completa
la máquina de `recalcular_tras_pago` (parcial/total/cascada a `cobrada`) y, al cancelarse,
reutiliza completo ADR-286 (`PagoClienteService.cancelar`/comisiones comprometidas).
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
from app.modules.facturacion.factura_agencia import FacturaAgencia  # noqa: F401 — registra la tabla
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
    db: Session, cat: dict[str, uuid.UUID], folio: str, *, subtotal: Decimal = Decimal("10000.00")
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
            fecha_inicio_campania=date(2026, 2, 1),
            fecha_fin_campania=date(2026, 2, 28),
            total_dias_campania=28,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=10,
            subtotal=subtotal,
            iva=iva,
            total=(subtotal + iva).quantize(Decimal("0.01")),
            estatus_orden="orden_cerrada",
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


def _crear_y_timbrar_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], numero: str = "FMEX-1001"
) -> tuple[str, uuid.UUID]:
    """Crea una OC cerrada, la factura (Ingreso), la timbra. Devuelve (factura_id, orden_id)."""
    orden_id = _orden(db, cat, f"OC-{numero}")
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
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    r2 = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={
            "folio_fiscal_sat": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
            "fecha_timbrado": "2026-03-02",
        },
        headers=_hdr("facturacion"),
    )
    assert r2.status_code == 200, r2.text
    return factura_id, orden_id


def _payload_nc(
    cat: dict[str, uuid.UUID],
    origen_id: str,
    *,
    numero_factura: str = "NC-2026-03-0001",
    monto: str = "2000.00",
    motivo: str = "descuento",
    ordenes_ids: list[str] | None = None,
    facturas_relacionadas_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "ordenes_ids": ordenes_ids if ordenes_ids is not None else [],
        "numero_factura": numero_factura,
        "descripcion_factura": "Nota de crédito por descuento comercial",
        "fecha_factura": "2026-03-10",
        "cuenta_contable_id": str(cat["cuenta_id"]),
        "metodo_pago_clave": "PUE",
        "forma_pago_clave": "99",
        "clave_prod_serv": "82101601",
        "clave_unidad": "E48",
        "moneda_sat": "MXN",
        "tipo_comprobante": "E",
        "facturas_relacionadas_ids": (
            facturas_relacionadas_ids if facturas_relacionadas_ids is not None else [origen_id]
        ),
        "motivo_nota_credito": motivo,
        "monto_nota_credito": monto,
    }


def _crear_nc(  # type: ignore[no-untyped-def]
    client: TestClient,
    cat: dict[str, uuid.UUID],
    origen_id: str,
    *,
    numero_factura: str = "NC-2026-03-0001",
    monto: str = "2000.00",
    motivo: str = "descuento",
    ordenes_ids: list[str] | None = None,
    facturas_relacionadas_ids: list[str] | None = None,
):
    return client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_nc(
            cat,
            origen_id,
            numero_factura=numero_factura,
            monto=monto,
            motivo=motivo,
            ordenes_ids=ordenes_ids,
            facturas_relacionadas_ids=facturas_relacionadas_ids,
        ),
        headers=_hdr("facturacion"),
    )


def _timbrar_nc(  # type: ignore[no-untyped-def]
    client: TestClient,
    nc_id: str,
    *,
    folio: str = "B2C3D4E5-F6A7-8901-BCDE-F12345678901",
):
    # Misma máquina de estados que cualquier factura: preparada → enviada_a_timbrado →
    # timbrada. La NC no se salta este paso, solo cambia el EFECTO de `timbrar()`.
    client.post(
        f"/api/v1/facturacion/clientes/{nc_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    return client.post(
        f"/api/v1/facturacion/clientes/{nc_id}/timbrar",
        json={"folio_fiscal_sat": folio, "fecha_timbrado": "2026-03-10"},
        headers=_hdr("facturacion"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Alta — validaciones
# ══════════════════════════════════════════════════════════════════════════════
def test_alta_rechaza_ordenes_ids_no_vacio(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id = _crear_y_timbrar_factura(client, db, cat)
    r = _crear_nc(client, cat, factura_id, ordenes_ids=[str(orden_id)])
    assert r.status_code == 422, r.text


def test_alta_rechaza_sin_factura_relacionada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    r = _crear_nc(client, cat, factura_id, facturas_relacionadas_ids=[])
    assert r.status_code == 422, r.text


def test_alta_rechaza_dos_facturas_relacionadas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_1, _ = _crear_y_timbrar_factura(client, db, cat, "FMEX-2001")
    factura_2, _ = _crear_y_timbrar_factura(client, db, cat, "FMEX-2002")
    r = _crear_nc(client, cat, factura_1, facturas_relacionadas_ids=[factura_1, factura_2])
    assert r.status_code == 422, r.text


def test_alta_rechaza_sin_motivo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    payload = _payload_nc(cat, factura_id)
    del payload["motivo_nota_credito"]
    r = client.post(
        "/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion")
    )
    assert r.status_code == 422, r.text


def test_alta_rechaza_folio_que_no_empieza_con_nc(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    r = _crear_nc(client, cat, factura_id, numero_factura="FMEX-9999")
    assert r.status_code == 422, r.text


def test_alta_rechaza_motivo_fuera_de_la_lista_fija(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    r = _crear_nc(client, cat, factura_id, motivo="otro_motivo_inventado")
    assert r.status_code == 422, r.text


def test_alta_rechaza_monto_cero_o_negativo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    r = _crear_nc(client, cat, factura_id, monto="0.00")
    assert r.status_code == 422, r.text


def test_alta_rechaza_factura_de_origen_inexistente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    r = _crear_nc(client, cat, str(uuid.uuid4()))
    assert r.status_code in (400, 404), r.text


# ══════════════════════════════════════════════════════════════════════════════
# Alta — caso feliz: hereda receptor/empresa, niega los montos
# ══════════════════════════════════════════════════════════════════════════════
def test_alta_hereda_receptor_empresa_y_forma_de_pago_y_niega_los_montos(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    origen = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}", headers=_hdr("facturacion")
    ).json()

    r = _crear_nc(client, cat, factura_id, monto="2000.00")
    assert r.status_code == 201, r.text
    nc = r.json()

    assert nc["tipo_comprobante"] == "E"
    assert nc["motivo_nota_credito"] == "descuento"
    assert nc["facturas_relacionadas_ids"] == [factura_id]
    assert nc["ordenes"] == []
    # Heredado de la factura de origen, NO lo que mandó el payload (que mandó "99").
    assert nc["razon_social_facturacion"] == origen["razon_social_facturacion"]
    assert nc["empresa_facturadora_id"] == origen["empresa_facturadora_id"]
    assert nc["metodo_pago_clave"] == "PUE"
    assert nc["forma_pago_clave"] == origen["forma_pago_clave"]
    # Montos NEGADOS (petición del usuario, "con signo negativo").
    assert Decimal(nc["subtotal_factura"]) == Decimal("-2000.00")
    assert Decimal(nc["iva_factura"]) == Decimal("-320.00")
    assert Decimal(nc["total_factura"]) == Decimal("-2320.00")


def test_archivo_plano_de_nota_credito_se_rechaza(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    nc = _crear_nc(client, cat, factura_id).json()
    r = client.get(
        f"/api/v1/facturacion/clientes/{nc['factura_id']}/archivo-plano",
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409, r.text


# ══════════════════════════════════════════════════════════════════════════════
# Timbrar — aplica el PagoCliente sintético (NO crea su propia CobranzaFactura)
# ══════════════════════════════════════════════════════════════════════════════
def test_timbrar_nota_credito_parcial_no_crea_cobranza_propia_y_baja_el_pendiente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)  # total 11600.00
    nc = _crear_nc(client, cat, factura_id, monto="2000.00").json()

    r = _timbrar_nc(client, nc["factura_id"])
    assert r.status_code == 200, r.text

    db.expire_all()
    # La NC NO tiene su propia CobranzaFactura.
    propia = db.query(CobranzaFactura).filter(
        CobranzaFactura.factura_id == uuid.UUID(nc["factura_id"])
    ).one_or_none()
    assert propia is None

    cobranza = db.query(CobranzaFactura).filter(
        CobranzaFactura.factura_id == uuid.UUID(factura_id)
    ).one()
    assert cobranza.estatus_cobro == EstatusCobro.COBRO_PARCIAL.value

    pago = db.query(PagoCliente).filter(
        PagoCliente.factura_egreso_id == uuid.UUID(nc["factura_id"])
    ).one()
    assert pago.cobranza_id == cobranza.cobranza_id
    assert pago.monto_aplicado == Decimal("2320.00")  # abs(total_factura) de la NC
    assert pago.metodo_pago_clave == "PUE"
    assert pago.numero_pago == "1"
    assert pago.estatus_pago == "pagado"


def test_timbrar_nota_credito_que_cubre_el_total_dispara_la_cascada_completa(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id = _crear_y_timbrar_factura(client, db, cat)  # total 11600.00
    # Monto tal que, con IVA, el total de la NC (negado) cubra exacto 11600.00:
    # 10000.00 * 1.16 = 11600.00
    nc = _crear_nc(client, cat, factura_id, monto="10000.00").json()

    r = _timbrar_nc(client, nc["factura_id"])
    assert r.status_code == 200, r.text

    db.expire_all()
    cobranza = db.query(CobranzaFactura).filter(
        CobranzaFactura.factura_id == uuid.UUID(factura_id)
    ).one()
    assert cobranza.estatus_cobro == EstatusCobro.COBRADA.value
    factura = db.get(FacturaCliente, uuid.UUID(factura_id))
    assert factura.estado_facturacion == EstadoFacturacion.COBRADA.value
    orden = db.get(OrdenCliente, orden_id)
    assert orden.estatus_orden == EstatusOrden.COBRADA.value


# ══════════════════════════════════════════════════════════════════════════════
# Cancelar — revierte el PagoCliente sintético (reutiliza ADR-286)
# ══════════════════════════════════════════════════════════════════════════════
def test_cancelar_nota_credito_revierte_el_pago_sintetico(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    nc = _crear_nc(client, cat, factura_id, monto="2000.00").json()
    _timbrar_nc(client, nc["factura_id"])

    r = client.post(
        f"/api/v1/facturacion/clientes/{nc['factura_id']}/cancelar", headers=_hdr("facturacion")
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado_facturacion"] == "cancelada"

    db.expire_all()
    pago = db.query(PagoCliente).filter(
        PagoCliente.factura_egreso_id == uuid.UUID(nc["factura_id"])
    ).one()
    assert pago.estatus_pago == "cancelado"
    assert pago.motivo_cancelacion == f"Nota de crédito {nc['numero_factura']} cancelada."

    cobranza = db.query(CobranzaFactura).filter(
        CobranzaFactura.factura_id == uuid.UUID(factura_id)
    ).one()
    assert cobranza.estatus_cobro == EstatusCobro.PENDIENTE.value


def test_cancelar_nota_credito_sin_timbrar_no_falla_sin_nada_que_revertir(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_y_timbrar_factura(client, db, cat)
    nc = _crear_nc(client, cat, factura_id, monto="2000.00").json()

    r = client.post(
        f"/api/v1/facturacion/clientes/{nc['factura_id']}/cancelar", headers=_hdr("facturacion")
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado_facturacion"] == "cancelada"
