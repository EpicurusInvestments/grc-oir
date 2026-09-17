"""Pruebas F2 · Tanda 2 — escritura, máquinas de estado y handoff con F1 (SQLite).

Lo central: **timbrar una FacturaCliente promueve su OrdenCliente a `facturada`**, y lo
hace de forma atómica. Además: la precondición `orden_cerrada`, el 1:1, la autorización
de Dirección/Admin sobre las facturas de proveedor, la asignación solo a OE cerradas, el
cálculo de la comisión de agencia y el puerto de exportación placeholder.
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
from app.modules.catalogos.constantes_sistema import (
    ConstanteSistema,  # noqa: F401 — el export al PAC consulta este catálogo
)
from app.modules.catalogos.contrato import Contrato  # noqa: F401 — ídem
from app.modules.catalogos.cuenta_contable import CuentaContable
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.facturacion.factura_cliente import FacturaCliente, _serie_desde_numero
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
            plaza_id=plaza_id,
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
    db: Session,
    cat: dict[str, uuid.UUID],
    estatus: str,
    folio: str,
    *,
    subtotal: Decimal = Decimal("10000.00"),
    inicio: date = date(2026, 2, 1),
    fin: date = date(2026, 2, 28),
    empresa_id: uuid.UUID | None = None,
    anunciante_id: uuid.UUID | None = None,
    directa: bool = False,
    producto: str | None = None,
    total_spots: int = 10,
    cantidad_spots_bonificables: int = 0,
) -> uuid.UUID:
    """Los parámetros opcionales existen para las pruebas de facturación múltiple, que
    necesitan órdenes que difieran en importe, periodo, emisora o receptor."""
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
            empresa_facturadora_id=empresa_id or cat["empresa_id"],
            vendedor_principal_id=cat["vendedor_id"],
            anunciante_id=anunciante_id or cat["anunciante_id"],
            agencia_id=cat["agencia_id"],
            facturacion_directa_cliente=directa,
            producto=producto,
            fecha_inicio_campania=inicio,
            fecha_fin_campania=fin,
            total_dias_campania=28,
            duracion_spot="30s",
            precio_unitario=Decimal("1000.00"),
            total_spots=total_spots,
            cantidad_spots_bonificables=cantidad_spots_bonificables,
            subtotal=subtotal,
            iva=iva,
            total=(subtotal + iva).quantize(Decimal("0.01")),
            estatus_orden=estatus,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return orden_id


def _orden_estacion(
    db: Session,
    cat: dict[str, uuid.UUID],
    orden_id: uuid.UUID,
    estatus: str,
    *,
    importe_estacion: Decimal = Decimal("10000.00"),
    importe_oir: Decimal = Decimal("3000.00"),
    iva_oir: Decimal = Decimal("480.00"),
    total_oir: Decimal = Decimal("3480.00"),
    importe_emisora: Decimal = Decimal("7000.00"),
    iva_emisora: Decimal = Decimal("1120.00"),
    total_emisora: Decimal = Decimal("8120.00"),
) -> uuid.UUID:
    oe_id = uuid.uuid4()
    db.add(
        OrdenEstacion(
            orden_estacion_id=oe_id,
            folio_orden_estacion=f"OE-{uuid.uuid4().hex[:6]}",
            orden_id=orden_id,
            anunciante_id=cat["anunciante_id"],
            vendedor_id=cat["vendedor_id"],
            estacion_id=cat["estacion_id"],
            plaza_id=cat["plaza_id"],
            duracion_spot="30s",
            precio_spot=Decimal("1000.00"),
            importe_estacion=importe_estacion,
            porcentaje_participacion_oir=Decimal("30.00"),
            importe_oir=importe_oir,
            iva_oir=iva_oir,
            total_oir=total_oir,
            importe_emisora=importe_emisora,
            iva_emisora=iva_emisora,
            total_emisora=total_emisora,
            estatus=estatus,
            created_by=ADMIN_ID,
        )
    )
    db.flush()
    return oe_id


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

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def _payload_factura(
    orden_id: uuid.UUID | list[uuid.UUID], cuenta_id: uuid.UUID, numero: str
) -> dict[str, object]:
    """Acepta una orden o varias: el alta recibe `ordenes_ids` desde ADR-064."""
    ids = orden_id if isinstance(orden_id, list) else [orden_id]
    return {
        "ordenes_ids": [str(o) for o in ids],
        "numero_factura": numero,
        "descripcion_factura": "Servicios de transmisión febrero 2026",
        "fecha_factura": "2026-03-01",
        "cuenta_contable_id": str(cuenta_id),
        "metodo_pago_clave": "PUE",
        "forma_pago_clave": "03",
    }


def _crear_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], numero: str = "F-0001"
) -> tuple[str, uuid.UUID]:
    orden_id = _orden(db, cat, "orden_cerrada", f"OC-{numero}")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], numero),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    return r.json()["factura_id"], orden_id


# ── Alta: precondición y herencia ─────────────────────────────────────────────
def test_no_se_factura_una_orden_que_no_esta_cerrada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "en_verificacion", "OC-NOCERRADA")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9001"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_alta_hereda_de_la_orden_y_calcula_iva_y_total(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id = _crear_factura(client, db, cat)
    r = client.get(f"/api/v1/facturacion/clientes/{factura_id}", headers=_hdr("facturacion"))
    cuerpo = r.json()
    # Heredado de la OC
    assert cuerpo["anunciante_id"] == str(cat["anunciante_id"])
    assert cuerpo["fecha_inicio_transmision"] == "2026-02-01"
    assert cuerpo["fecha_fin_transmision"] == "2026-02-28"
    assert cuerpo["subtotal_factura"] == "10000.00"
    # La OC tiene agencia y NO es facturación directa → receptor = agencia
    assert cuerpo["razon_social_facturacion"] == "Agencia Uno"
    assert cuerpo["rfc_facturacion"] == "AGU900101AB1"
    # Calculado
    assert cuerpo["iva_factura"] == "1600.00"
    assert cuerpo["total_factura"] == "11600.00"
    assert cuerpo["estado_facturacion"] == "preparada"


def test_alta_devuelve_el_folio_de_la_orden_sin_necesidad_de_un_get(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """ADR-055: el folio viaja denormalizado desde la respuesta del POST, no solo tras
    un GET posterior — igual en las transiciones (enviar a timbrado, timbrar, etc.)."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-CONFOLIO")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9002"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["folio_orden"] == "OC-CONFOLIO"


def test_no_se_aceptan_campos_calculados_del_cliente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-FORBID")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9003")
    payload["total_factura"] = "1.00"  # calculado: el schema debe rechazarlo
    r = client.post("/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion"))
    assert r.status_code == 422


def test_una_orden_solo_admite_una_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _, orden_id = _crear_factura(client, db, cat)
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9004"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "conflicto"


# ── `numero_factura`: formato LETRA-NÚMEROS y unicidad (bug real) ──────────────
def test_numero_factura_se_normaliza_a_mayusculas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-MINUS")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "f-9100"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["numero_factura"] == "F-9100"


@pytest.mark.parametrize(
    "numero",
    [
        "F9100",  # sin guion
        "FA-9100",  # más de una letra antes del guion
        "F-91A0",  # no todo dígitos después del guion
        "9-9100",  # empieza con dígito, no con letra
        "F-",  # sin dígitos después del guion
        "-9100",  # sin letra antes del guion
    ],
)
def test_numero_factura_rechaza_formato_invalido(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], numero: str
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-FORMATO")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], numero),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 422, r.text


def test_numero_factura_rechaza_duplicado_entre_ordenes_distintas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El número de factura es único en TODO el sistema, no solo por orden."""
    _crear_factura(client, db, cat, "F-9200")
    otra_orden = _orden(db, cat, "orden_cerrada", "OC-OTRANUM")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        # Minúsculas a propósito: debe chocar igual, ya normalizado a mayúsculas.
        json=_payload_factura(otra_orden, cat["cuenta_id"], "f-9200"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["codigo"] == "conflicto"
    assert "F-9200" in r.json()["error"]["mensaje"]


def test_existe_numero_factura_endpoint_para_validacion_en_vivo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Endpoint que consulta el formulario al perder el foco del campo, ANTES de
    intentar guardar todo — no lanza, solo informa `existe: bool`."""
    _crear_factura(client, db, cat, "F-9210")

    r = client.get(
        "/api/v1/facturacion/clientes/existe-numero-factura",
        params={"numero_factura": "F-9210"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"existe": True}

    # Minúsculas y espacios a propósito: mismo criterio case-insensitive que el alta.
    r = client.get(
        "/api/v1/facturacion/clientes/existe-numero-factura",
        params={"numero_factura": " f-9210 "},
        headers=_hdr("facturacion"),
    )
    assert r.json() == {"existe": True}

    r = client.get(
        "/api/v1/facturacion/clientes/existe-numero-factura",
        params={"numero_factura": "F-9211"},
        headers=_hdr("facturacion"),
    )
    assert r.json() == {"existe": False}


def test_existe_numero_factura_excluye_la_propia_factura_al_editar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_factura(client, db, cat, "F-9212")

    r = client.get(
        "/api/v1/facturacion/clientes/existe-numero-factura",
        params={"numero_factura": "F-9212", "excluir_id": factura_id},
        headers=_hdr("facturacion"),
    )
    assert r.json() == {"existe": False}


def test_editar_numero_factura_rechaza_duplicado_contra_otra_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_a, _ = _crear_factura(client, db, cat, "F-9300")
    factura_b, _ = _crear_factura(client, db, cat, "F-9301")
    r = client.put(
        f"/api/v1/facturacion/clientes/{factura_b}",
        json={"numero_factura": "F-9300"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409, r.text


def test_editar_numero_factura_permite_conservar_el_mismo_valor(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """No debe chocar consigo misma: `excluir_id` tiene que excluir la propia factura."""
    factura_id, _ = _crear_factura(client, db, cat, "F-9400")
    r = client.put(
        f"/api/v1/facturacion/clientes/{factura_id}",
        json={"numero_factura": "F-9400", "descripcion_factura": "Actualizada"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["numero_factura"] == "F-9400"


# ── Facturas relacionadas (N:N, ADR-062) ───────────────────────────────────────
def test_alta_admite_varias_facturas_relacionadas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    id_a, _ = _crear_factura(client, db, cat, "F-9005")
    id_b, _ = _crear_factura(client, db, cat, "F-9006")
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-C")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9007")
    payload["facturas_relacionadas_ids"] = [id_a, id_b]
    r = client.post("/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion"))
    assert r.status_code == 201, r.text
    assert sorted(r.json()["facturas_relacionadas_ids"]) == sorted([id_a, id_b])

    releida = client.get(
        f"/api/v1/facturacion/clientes/{r.json()['factura_id']}", headers=_hdr("facturacion")
    )
    assert sorted(releida.json()["facturas_relacionadas_ids"]) == sorted([id_a, id_b])


def test_alta_deduplica_facturas_relacionadas_repetidas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    id_a, _ = _crear_factura(client, db, cat, "F-9008")
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-DUP-B")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9009")
    payload["facturas_relacionadas_ids"] = [id_a, id_a]
    r = client.post("/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion"))
    assert r.status_code == 201, r.text
    assert r.json()["facturas_relacionadas_ids"] == [id_a]


def test_las_transiciones_no_pierden_las_facturas_relacionadas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo bug que ADR-055 resolvió para `folio_orden`: la respuesta de una transición
    debe traer `facturas_relacionadas_ids` ya resuelto, no vacío hasta el próximo GET."""
    id_a, _ = _crear_factura(client, db, cat, "F-9010")
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-TRANS-B")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9011")
    payload["facturas_relacionadas_ids"] = [id_a]
    creada = client.post(
        "/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion")
    )
    fid = creada.json()["factura_id"]

    r = client.post(
        f"/api/v1/facturacion/clientes/{fid}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    assert r.json()["facturas_relacionadas_ids"] == [id_a]


def test_alta_rechaza_una_factura_relacionada_inexistente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-404")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9012")
    payload["facturas_relacionadas_ids"] = [str(uuid.uuid4())]
    r = client.post("/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion"))
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


# ── EL HANDOFF ────────────────────────────────────────────────────────────────
def test_timbrar_promueve_la_orden_a_facturada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La prueba central de la Tanda 2 (ficha de F2)."""
    factura_id, orden_id = _crear_factura(client, db, cat)

    # `preparada` todavía NO mueve la orden.
    assert db.get(OrdenCliente, orden_id).estatus_orden == "orden_cerrada"

    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    assert r.json()["estado_facturacion"] == "enviada_a_timbrado"
    # `enviada_a_timbrado` TAMPOCO la mueve.
    db.expire_all()
    assert db.get(OrdenCliente, orden_id).estatus_orden == "orden_cerrada"

    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "ABC-123-DEF", "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado_facturacion"] == "timbrada"
    assert r.json()["folio_fiscal_sat"] == "ABC-123-DEF"

    # ── el handoff ──
    db.expire_all()
    assert db.get(OrdenCliente, orden_id).estatus_orden == "facturada"


def test_timbrar_es_idempotente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id = _crear_factura(client, db, cat)
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    cuerpo = {"folio_fiscal_sat": "ABC-123", "fecha_timbrado": "2026-03-02"}
    url = f"/api/v1/facturacion/clientes/{factura_id}/timbrar"
    r1 = client.post(url, json=cuerpo, headers=_hdr("facturacion"))
    r2 = client.post(url, json=cuerpo, headers=_hdr("facturacion"))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["estado_facturacion"] == "timbrada"
    db.expire_all()
    assert db.get(OrdenCliente, orden_id).estatus_orden == "facturada"


def test_si_la_orden_no_admite_facturada_el_timbrado_se_revierte(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Atomicidad: el handoff y el timbrado son una sola transacción.

    Se fuerza el escenario moviendo la OC a `cancelada` DESPUÉS de crear la factura:
    `marcar_facturada` la rechaza y la excepción debe abortar también el timbrado.
    """
    factura_id, orden_id = _crear_factura(client, db, cat)
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    oc = db.get(OrdenCliente, orden_id)
    oc.estatus_orden = "cancelada"
    db.commit()

    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "X", "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "transicion_invalida"

    # La factura NO quedó timbrada.
    db.rollback()
    db.expire_all()
    assert db.get(FacturaCliente, uuid.UUID(factura_id)).estado_facturacion == "enviada_a_timbrado"
    assert db.get(FacturaCliente, uuid.UUID(factura_id)).folio_fiscal_sat is None


# ── Máquina de estados de FacturaCliente ──────────────────────────────────────
def test_transicion_invalida_da_409(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_factura(client, db, cat)
    # `preparada` → `timbrada` se salta un paso.
    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "X", "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "transicion_invalida"


def test_no_se_edita_una_factura_timbrada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_factura(client, db, cat)
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "X", "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    r = client.put(
        f"/api/v1/facturacion/clientes/{factura_id}",
        json={"descripcion_factura": "Otra cosa"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409


# ── Exportación al PAC (layout real V40) ──────────────────────────────────────
def test_el_archivo_plano_sale_en_el_layout_del_pac(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El endpoint entrega el layout real. Los detalles del formato se prueban aparte, en
    `test_f2_03_timbrado_pac_v40.py` (incluida la fila regenerada byte a byte)."""
    factura_id, _ = _crear_factura(client, db, cat)
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    texto = r.content.decode("cp1252")
    assert texto.startswith("XXXINICIO\r\n")
    assert "XXXFINDO" in texto
    assert "RFCRecep         AGU900101AB1" in texto  # receptor = agencia de la OC
    assert "VlrPagar         11600.00" in texto
    assert "Serie            F" in texto  # ADR-060 bis: se deriva de "F-0001"
    # El nombre del archivo usa esa misma Serie derivada (antes "SN" al no haber catálogo).
    assert 'filename="FACTURA_33_F_F-0001.txt"' in r.headers["content-disposition"]


def test_el_endpoint_avisa_de_los_campos_fiscales_que_faltan(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Sin constantes fiscales en el catálogo el archivo sale, pero incompleto: la
    cabecera lo dice para que nadie lo mande al PAC creyéndolo listo."""
    factura_id, _ = _crear_factura(client, db, cat)
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    faltantes = r.headers["x-campos-faltantes"]
    assert "Detalle.ClaveProdServ" in faltantes
    assert "AGREGADOS.UsoCFDI" in faltantes
    # La cabecera debe ser visible para el navegador, o la pantalla no podría avisar.
    assert "X-Campos-Faltantes" in r.headers["access-control-expose-headers"]


def test_el_archivo_plano_lleva_los_spots_reales_no_uno_fijo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Bug real: `Detalle.CANT` era "1" fijo sin importar cuántos spots tuviera la
    orden. La OC de `cat` (vía `_orden`) es 10 spots a $1000.00 c/u = $10,000.00."""
    factura_id, _ = _crear_factura(client, db, cat)
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    texto = r.content.decode("cp1252")
    lineas = texto.split("\r\n")
    linea_detalle = lineas[lineas.index("================ Detalle") + 2]

    assert linea_detalle[49:59].strip() == "10"  # Detalle.CANT: spots reales
    assert linea_detalle[74:88].strip() == "1000.00"  # Detalle.COSTO = 10000.00 / 10
    assert linea_detalle[88:114].strip() == "10000.00"  # Detalle.IMPORTE = subtotal


def test_el_archivo_plano_con_bonificables_usa_spots_facturables_en_cant(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Bug real corregido (ADR-069): con Spots Bonificables (ADR-067), `subtotal` ya
    representa solo lo FACTURABLE, pero `Detalle.CANT` seguía trayendo el total de spots
    (con bonificables incluidos) — `Detalle.COSTO` salía diluido por debajo del
    `precio_unitario` real. 100 spots a $1.00, 5 bonificables -> 95 facturables ($95.00)."""
    orden_id = _orden(
        db,
        cat,
        "orden_cerrada",
        "OC-BONIF",
        subtotal=Decimal("95.00"),
        total_spots=100,
        cantidad_spots_bonificables=5,
    )
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9600"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    factura_id = r.json()["factura_id"]

    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    texto = r.content.decode("cp1252")
    lineas = texto.split("\r\n")
    linea_detalle = lineas[lineas.index("================ Detalle") + 2]

    assert linea_detalle[49:59].strip() == "95"  # Detalle.CANT: spots FACTURABLES, no 100
    assert linea_detalle[74:88].strip() == "1.00"  # Detalle.COSTO reconstruye precio_unitario
    assert linea_detalle[88:114].strip() == "95.00"  # Detalle.IMPORTE = subtotal, sin cambios


# ── Serie derivada del número de factura (ADR-060 bis) ────────────────────────
@pytest.mark.parametrize(
    ("numero", "esperado"),
    [
        ("A-0010890", "A"),
        ("B-001002TYU", "B"),
        ("F-0001", "F"),
        ("SINGUION", None),  # sin "-": no hay de dónde derivar la serie
        ("-0001", None),  # prefijo vacío antes del guion
        ("  C -0001", "C"),  # espacios alrededor del prefijo se recortan
    ],
)
def test_serie_desde_numero(numero: str, esperado: str | None) -> None:
    assert _serie_desde_numero(numero) == esperado


# ── Domicilio estructurado en el archivo plano (ADR-059) ──────────────────────
def test_domicilio_del_emisor_desglosado_si_empresa_facturadora_lo_tiene(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Con `EmpresaFacturadora` capturada por CP (ADR-059), el PAC recibe Calle/Colonia/
    Municipio/… de verdad — y de paso resuelve AGREGADOS.LugarExpedicion (mismo CP)."""
    empresa = db.get(EmpresaFacturadora, cat["empresa_id"])
    empresa.calle = "Av. Constituyentes"
    empresa.numero_exterior = "1154"
    empresa.colonia = "Lomas Altas"
    empresa.municipio = "Miguel Hidalgo"
    empresa.estado = "Ciudad de México"
    empresa.codigo_postal = "11950"
    db.commit()

    factura_id, _ = _crear_factura(client, db, cat)
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    texto = r.content.decode("cp1252")
    assert "Calle            Av. Constituyentes" in texto
    assert "Colonia          Lomas Altas" in texto
    assert "CodigoPostal     11950" in texto  # ExEmisorDomFiscal
    assert "LugarExpedicion    11950" in texto  # AGREGADOS (columna 19)
    faltantes = r.headers["x-campos-faltantes"]
    assert "domicilio del emisor" not in faltantes
    assert "AGREGADOS.LugarExpedicion" not in faltantes


def test_domicilio_del_receptor_desglosado_solo_si_es_directa(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El receptor de esta OC es la AGENCIA (fixture `cat` estándar) — `Agencia` todavía
    no tiene domicilio estructurado (ADR-059 solo cubrió Anunciante/EmpresaFacturadora),
    así que el receptor NO sale desglosado aunque el Anunciante sí tenga uno capturado."""
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.calle = "Insurgentes Sur"
    anunciante.colonia = "Del Valle"
    anunciante.municipio = "Benito Juárez"
    anunciante.estado = "Ciudad de México"
    anunciante.codigo_postal = "03100"
    db.commit()

    factura_id, _ = _crear_factura(client, db, cat)
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    texto = r.content.decode("cp1252")
    assert "Insurgentes Sur" not in texto  # el receptor es la agencia, no el anunciante
    assert "RFCRecep         AGU900101AB1" in texto  # sigue siendo la agencia


def test_domicilio_del_receptor_desglosado_si_es_directa_y_anunciante_lo_tiene(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Facturación directa (sin agencia): el receptor SÍ es el Anunciante, y su domicilio
    estructurado (ADR-059) sale desglosado en `ExReceptorDomFiscal`."""
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.calle = "Insurgentes Sur"
    anunciante.numero_exterior = "800"
    anunciante.colonia = "Del Valle"
    anunciante.municipio = "Benito Juárez"
    anunciante.estado = "Ciudad de México"
    anunciante.codigo_postal = "03100"
    db.commit()

    orden_id = uuid.uuid4()
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden="OC-DIRECTA",
            numero_orden_cliente="NUM-OC-DIRECTA",
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=cat["empresa_id"],
            vendedor_principal_id=cat["vendedor_id"],
            anunciante_id=cat["anunciante_id"],
            agencia_id=None,  # trato directo: el receptor es el Anunciante
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
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9013"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    factura_id = r.json()["factura_id"]

    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    texto = r.content.decode("cp1252")
    assert "Insurgentes Sur" in texto
    assert "CodigoPostal     03100" in texto
    assert "domicilio del receptor" not in r.headers["x-campos-faltantes"]


# ── RegimenFiscal: columna propia por entidad, ya no catálogo global (bug real) ─
def test_regimen_fiscal_emisor_sale_de_empresa_facturadora(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    empresa = db.get(EmpresaFacturadora, cat["empresa_id"])
    empresa.regimen_fiscal = "601"
    db.commit()

    factura_id, _ = _crear_factura(client, db, cat, "F-9500")
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert "AGREGADOS.Regimen" not in r.headers["x-campos-faltantes"]


def test_regimen_fiscal_receptor_sale_de_la_agencia_cuando_no_es_directa(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La OC de `cat` factura vía agencia (no directa): el régimen del RECEPTOR debe
    salir de la Agencia, no del Anunciante (que en esta prueba se deja SIN capturar,
    para probar que no hay un fallback incorrecto)."""
    agencia = db.get(Agencia, cat["agencia_id"])
    agencia.regimen_fiscal = "601"
    db.commit()

    factura_id, _ = _crear_factura(client, db, cat, "F-9501")
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert "ExReceptor.RegimenFiscal" not in r.headers["x-campos-faltantes"]


def test_regimen_fiscal_receptor_no_sale_del_anunciante_si_el_receptor_es_la_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Lo contrario del caso anterior: capturar el régimen SOLO en el Anunciante, con una
    OC que factura vía agencia, no debe resolver nada — confirma que no hay cruce entre
    las dos fuentes posibles del régimen del receptor."""
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.regimen_fiscal = "601"
    db.commit()

    factura_id, _ = _crear_factura(client, db, cat, "F-9502")
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert "ExReceptor.RegimenFiscal" in r.headers["x-campos-faltantes"]


def test_regimen_fiscal_receptor_sale_del_anunciante_cuando_es_directa(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.regimen_fiscal = "612"
    db.commit()

    orden_id = uuid.uuid4()
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden="OC-RFDIRECTA",
            numero_orden_cliente="NUM-OC-RFDIRECTA",
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=cat["empresa_id"],
            vendedor_principal_id=cat["vendedor_id"],
            anunciante_id=cat["anunciante_id"],
            agencia_id=None,  # trato directo: el receptor es el Anunciante
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
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9503"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    factura_id = r.json()["factura_id"]

    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert "ExReceptor.RegimenFiscal" not in r.headers["x-campos-faltantes"]


# ── UsoCFDI: default en Anunciante, editable por factura (bug real) ────────────
def test_uso_cfdi_se_precarga_del_anunciante_cuando_es_directa(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.uso_cfdi_default = "G03"
    db.commit()

    orden_id = uuid.uuid4()
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden="OC-UCFDI1",
            numero_orden_cliente="NUM-OC-UCFDI1",
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=cat["empresa_id"],
            vendedor_principal_id=cat["vendedor_id"],
            anunciante_id=cat["anunciante_id"],
            agencia_id=None,  # trato directo: el receptor es el Anunciante
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
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9600"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["uso_cfdi"] == "G03"

    r = client.get(
        f"/api/v1/facturacion/clientes/{r.json()['factura_id']}/archivo-plano",
        headers=_hdr("facturacion"),
    )
    assert "AGREGADOS.UsoCFDI" not in r.headers["x-campos-faltantes"]


def test_uso_cfdi_no_se_precarga_si_el_receptor_es_la_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La OC de `cat` factura vía agencia: aunque el Anunciante SÍ tenga un default
    capturado, no hay de dónde sugerirlo (la Agencia no tiene esa columna) — queda sin
    capturar, no se cuela por error el del anunciante."""
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.uso_cfdi_default = "G03"
    db.commit()

    factura_id, _ = _crear_factura(client, db, cat, "F-9601")
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert "AGREGADOS.UsoCFDI" in r.headers["x-campos-faltantes"]


def test_uso_cfdi_override_explicito_prevalece_sobre_el_default(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    anunciante = db.get(Anunciante, cat["anunciante_id"])
    anunciante.uso_cfdi_default = "G03"
    db.commit()

    orden_id = uuid.uuid4()
    db.add(
        OrdenCliente(
            orden_id=orden_id,
            folio_orden="OC-UCFDI2",
            numero_orden_cliente="NUM-OC-UCFDI2",
            fecha_venta=date(2026, 1, 10),
            anio_venta=2026,
            mes_venta=1,
            empresa_facturadora_id=cat["empresa_id"],
            vendedor_principal_id=cat["vendedor_id"],
            anunciante_id=cat["anunciante_id"],
            agencia_id=None,
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
    db.commit()

    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9602")
    payload["uso_cfdi"] = "P01"
    r = client.post(
        "/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion")
    )
    assert r.status_code == 201, r.text
    assert r.json()["uso_cfdi"] == "P01"


def test_uso_cfdi_capturable_a_mano_aunque_el_receptor_sea_la_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-UCFDI3")
    db.commit()

    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9603")
    payload["uso_cfdi"] = "S01"
    r = client.post(
        "/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion")
    )
    assert r.status_code == 201, r.text
    assert r.json()["uso_cfdi"] == "S01"


# ── FormaPago: se captura por factura, ya no sale del catálogo global (bug real) ─
def test_forma_pago_clave_se_captura_y_llega_al_archivo_plano(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Antes se resolvía sola con `_constante_unica("FormaPago")` — dejó de servir en
    cuanto ese catálogo tuvo más de una activa (mismo bug que RegimenFiscal/UsoCFDI).
    Ahora se captura al dar de alta, igual que MetodoPago."""
    factura_id, _ = _crear_factura(client, db, cat, "F-9700")
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}", headers=_hdr("facturacion")
    )
    assert r.json()["forma_pago_clave"] == "03"  # el default de _payload_factura

    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert "AGREGADOS.MedioPago" not in r.headers["x-campos-faltantes"]


def test_forma_pago_clave_es_obligatoria_en_el_alta(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-SINFORMAPAGO")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-9701")
    del payload["forma_pago_clave"]
    r = client.post(
        "/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion")
    )
    assert r.status_code == 422, r.text


def test_una_factura_cancelada_no_se_exporta(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, _ = _crear_factura(client, db, cat)
    client.post(f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion"))
    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert r.status_code == 409


# ── Facturas de proveedor: autorización de Dirección/Admin ────────────────────
def _crear_factura_afiliado(client: TestClient, cat: dict[str, uuid.UUID]) -> str:
    r = client.post(
        "/api/v1/facturacion/afiliados",
        json={
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_emisora": "AF-77",
            "fecha_factura_afiliado": "2026-03-02",
            "monto_factura_afiliado": "7000.00",
            "iva_factura_afiliado": "1120.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["total_factura_afiliado"] == "8120.00"  # calculado
    assert r.json()["razon_social_afiliada"] == "Afiliado Uno SA de CV"  # heredado
    return r.json()["factura_afiliado_id"]


def test_cxp_no_puede_autorizar_su_propia_factura(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_afiliado(client, cat)
    r = client.post(
        f"/api/v1/facturacion/afiliados/{fid}/estatus",
        json={"estatus": "en_revision"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200
    # Ni por el canal operativo ni por el dedicado: CxP no autoriza.
    r = client.post(
        f"/api/v1/facturacion/afiliados/{fid}/estatus",
        json={"estatus": "autorizada"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "sin_permiso"
    r = client.post(f"/api/v1/facturacion/afiliados/{fid}/autorizar", headers=_hdr("cxp"))
    assert r.status_code == 403


@pytest.mark.parametrize("area", ["direccion", "admin"])
def test_direccion_y_admin_si_autorizan(
    client: TestClient, cat: dict[str, uuid.UUID], area: str
) -> None:
    fid = _crear_factura_afiliado(client, cat)
    client.post(
        f"/api/v1/facturacion/afiliados/{fid}/estatus",
        json={"estatus": "en_revision"},
        headers=_hdr("cxp"),
    )
    r = client.post(f"/api/v1/facturacion/afiliados/{fid}/autorizar", headers=_hdr(area))
    assert r.status_code == 200, area
    assert r.json()["estatus_factura_afiliado"] == "autorizada"


def test_ventas_no_captura_costos(client: TestClient, cat: dict[str, uuid.UUID]) -> None:
    r = client.post(
        "/api/v1/facturacion/afiliados",
        json={
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_emisora": "AF-99",
            "fecha_factura_afiliado": "2026-03-02",
            "monto_factura_afiliado": "1.00",
            "iva_factura_afiliado": "0.16",
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 403


def test_facturacion_no_captura_costos_y_cxp_no_captura_facturas_cliente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Las dos claves de RBAC (ADR-044) no se cruzan."""
    r = client.post(
        "/api/v1/facturacion/afiliados",
        json={
            "afiliado_id": str(cat["afiliado_id"]),
            "factura_emisora": "AF-88",
            "fecha_factura_afiliado": "2026-03-02",
            "monto_factura_afiliado": "1.00",
            "iva_factura_afiliado": "0.16",
        },
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 403

    orden_id = _orden(db, cat, "orden_cerrada", "OC-CRUCE")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9014"),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 403


# ── Reparto a OrdenEstacion cerradas ──────────────────────────────────────────
def test_solo_se_asigna_costo_a_una_oe_cerrada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_afiliado(client, cat)
    orden_id = _orden(db, cat, "en_transmision", "OC-OE")
    oe_abierta = _orden_estacion(db, cat, orden_id, "en_transmision")
    oe_cerrada = _orden_estacion(db, cat, orden_id, "cerrada")
    db.commit()

    r = client.post(
        f"/api/v1/facturacion/afiliados/{fid}/ordenes",
        json={"orden_estacion_id": str(oe_abierta), "monto_asignado": "100.00"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"

    r = client.post(
        f"/api/v1/facturacion/afiliados/{fid}/ordenes",
        json={"orden_estacion_id": str(oe_cerrada), "monto_asignado": "100.00"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201

    # La misma OE dos veces en la MISMA factura → 409 legible, no error de integridad.
    r = client.post(
        f"/api/v1/facturacion/afiliados/{fid}/ordenes",
        json={"orden_estacion_id": str(oe_cerrada), "monto_asignado": "1.00"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 409


# ── Comisión de agencia ───────────────────────────────────────────────────────
def test_comision_se_calcula_sobre_el_total_de_la_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-AG")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_agencia": "2026-03-03",
            "monto_factura_agencia": "1160.00",
            "iva_factura_agencia": "185.60",
            "porcentaje_comision_agencia": "10.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    # OrdenCliente.total = 11600.00 · 10% = 1160.00
    assert r.json()["comision_agencia"] == "1160.00"
    assert r.json()["total_factura_agencia"] == "1345.60"


def test_el_porcentaje_se_sugiere_del_catalogo_si_no_viene(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-AG2")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_agencia": "2026-03-03",
            "monto_factura_agencia": "100.00",
            "iva_factura_agencia": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201
    assert r.json()["porcentaje_comision_agencia"] == "10.00"  # default del catálogo
    assert r.json()["comision_agencia"] == "1160.00"


def test_alta_factura_agencia_trae_agencia_y_orden_denormalizados(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El alta ya trae `agencia`/`folio_orden`/`anunciante`/`producto`/`orden_total` en
    la MISMA respuesta (sin esperar al próximo GET) — mismo criterio que
    `_enriquecida()` en `factura_afiliado.py`."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-AG-ENRIQ", producto="Spot radio mayo")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_agencia": "2026-03-03",
            "monto_factura_agencia": "1160.00",
            "iva_factura_agencia": "185.60",
            "porcentaje_comision_agencia": "10.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["agencia"] == "Agencia Uno"
    assert body["folio_orden"] == "OC-AG-ENRIQ"
    assert body["numero_orden_cliente"] == "NUM-OC-AG-ENRIQ"
    assert body["anunciante"] == "Anunciante Uno"
    assert body["producto"] == "Spot radio mayo"
    assert body["orden_total"] == "11600.00"

    detalle = client.get(
        f"/api/v1/facturacion/agencias/{body['factura_agencia_id']}", headers=_hdr("cxp")
    ).json()
    assert detalle["agencia"] == "Agencia Uno"
    assert detalle["folio_orden"] == "OC-AG-ENRIQ"

    lista = client.get(
        "/api/v1/facturacion/agencias",
        params={"agencia_id": str(cat["agencia_id"]), "size": 100},
        headers=_hdr("cxp"),
    ).json()
    en_lista = next(
        f for f in lista["items"] if f["factura_agencia_id"] == body["factura_agencia_id"]
    )
    assert en_lista["agencia"] == "Agencia Uno"
    assert en_lista["folio_orden"] == "OC-AG-ENRIQ"


def test_factura_agencia_captura_y_edita_archivo_pdf_xml(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """ADR-079: la factura de la agencia se sube en PDF y XML por separado, mismo
    criterio que ADR-070 en FacturaAfiliado — se capturan como referencias (claves de
    almacenamiento ya subidas), no como el archivo mismo en este endpoint."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-AG-ARCHIVO")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_agencia": "2026-03-03",
            "monto_factura_agencia": "1160.00",
            "iva_factura_agencia": "185.60",
            "archivo_pdf_path": "facturacion/proveedor/agencia/pdf/abc_factura.pdf",
            "archivo_xml_path": "facturacion/proveedor/agencia/xml/abc_factura.xml",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["archivo_pdf_path"] == "facturacion/proveedor/agencia/pdf/abc_factura.pdf"
    assert r.json()["archivo_xml_path"] == "facturacion/proveedor/agencia/xml/abc_factura.xml"
    fid = r.json()["factura_agencia_id"]

    r = client.put(
        f"/api/v1/facturacion/agencias/{fid}",
        json={"archivo_pdf_path": "facturacion/proveedor/agencia/pdf/nuevo.pdf"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["archivo_pdf_path"] == "facturacion/proveedor/agencia/pdf/nuevo.pdf"
    # No se tocó al editar: sigue el mismo XML de antes.
    assert r.json()["archivo_xml_path"] == "facturacion/proveedor/agencia/xml/abc_factura.xml"


def test_ordenes_facturables_agencia_solo_lista_las_cerradas_de_esa_agencia(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    from app.modules.catalogos.agencia import Agencia

    orden_cerrada = _orden(db, cat, "orden_cerrada", "OC-AG-COMBO", producto="Radio spot")
    _orden(db, cat, "en_transmision", "OC-AG-NOCERRADA")  # no debe aparecer

    otra_agencia_id = uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=otra_agencia_id,
            nombre_agencia="Agencia Dos",
            rfc_agencia="ADS900101AB2",
            porcentaje_comision_agencia_default=Decimal("12.50"),
        )
    )
    db.commit()

    r = client.get(
        "/api/v1/facturacion/agencias/ordenes-facturables",
        params={"agencia_id": str(cat["agencia_id"])},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["orden_id"] == str(orden_cerrada)
    assert items[0]["folio_orden"] == "OC-AG-COMBO"
    assert items[0]["anunciante"] == "Anunciante Uno"
    assert items[0]["producto"] == "Radio spot"
    assert items[0]["total"] == "11600.00"
    assert items[0]["porcentaje_comision_agencia_default"] == "10.00"

    # Una agencia SIN órdenes cerradas propias → combo vacío (no las de otra agencia).
    vacio = client.get(
        "/api/v1/facturacion/agencias/ordenes-facturables",
        params={"agencia_id": str(otra_agencia_id)},
        headers=_hdr("cxp"),
    ).json()
    assert vacio == []


def test_editar_factura_agencia_permite_reasignar_agencia_y_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: la edición hace todo lo que hace el alta — reasignar
    agencia y orden relacionada, recalculando la comisión contra la NUEVA orden."""
    from app.modules.catalogos.agencia import Agencia

    orden_id = _orden(db, cat, "orden_cerrada", "OC-AG-EDIT-1", subtotal=Decimal("10000.00"))
    otra_agencia_id = uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=otra_agencia_id,
            nombre_agencia="Agencia Dos",
            rfc_agencia="ADS900101AB3",
            porcentaje_comision_agencia_default=Decimal("20.00"),
        )
    )
    db.commit()
    otra_orden_id = _orden(db, cat, "orden_cerrada", "OC-AG-EDIT-2", subtotal=Decimal("5000.00"))
    db.commit()

    alta = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_agencia": "2026-03-03",
            "monto_factura_agencia": "1160.00",
            "iva_factura_agencia": "185.60",
            "porcentaje_comision_agencia": "10.00",
        },
        headers=_hdr("cxp"),
    )
    assert alta.status_code == 201, alta.text
    fid = alta.json()["factura_agencia_id"]
    # OrdenCliente.total = 5000 * 1.16 = 5800.00 · 20% = 1160.00
    r = client.put(
        f"/api/v1/facturacion/agencias/{fid}",
        json={
            "agencia_id": str(otra_agencia_id),
            "orden_id": str(otra_orden_id),
            "porcentaje_comision_agencia": "20.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agencia_id"] == str(otra_agencia_id)
    assert body["orden_id"] == str(otra_orden_id)
    assert body["agencia"] == "Agencia Dos"
    assert body["folio_orden"] == "OC-AG-EDIT-2"
    assert body["comision_agencia"] == "1160.00"


def test_editar_factura_agencia_agencia_inexistente_400(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_agencia_simple(client, db, cat, folio="OC-AG-SIMPLE-1")
    r = client.put(
        f"/api/v1/facturacion/agencias/{fid}",
        json={"agencia_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_editar_factura_agencia_orden_inexistente_400(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_agencia_simple(client, db, cat, folio="OC-AG-SIMPLE-2")
    r = client.put(
        f"/api/v1/facturacion/agencias/{fid}",
        json={"orden_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_editar_factura_agencia_autorizada_no_permite_reasignar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_agencia_simple(client, db, cat, folio="OC-AG-SIMPLE-3")
    client.post(
        f"/api/v1/facturacion/agencias/{fid}/estatus",
        json={"estatus": "en_revision"},
        headers=_hdr("cxp"),
    )
    client.post(f"/api/v1/facturacion/agencias/{fid}/autorizar", headers=_hdr("direccion"))

    r = client.put(
        f"/api/v1/facturacion/agencias/{fid}",
        json={"agencia_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 409


def test_lista_facturas_agencia_ordena_por_mas_reciente_primero(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo criterio que `FacturaAfiliado` (ADR-086): ordena por `created_at`, no por
    `fecha_factura_agencia` (a propósito invertida respecto al orden de captura)."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-AG-ORDEN")
    db.commit()

    primera = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "folio_factura_agencia": "AG-ORDEN-1",
            "fecha_factura_agencia": "2026-06-01",
            "monto_factura_agencia": "100.00",
            "iva_factura_agencia": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert primera.status_code == 201, primera.text

    segunda = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "folio_factura_agencia": "AG-ORDEN-2",
            "fecha_factura_agencia": "2026-01-01",
            "monto_factura_agencia": "100.00",
            "iva_factura_agencia": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert segunda.status_code == 201, segunda.text

    lista = client.get(
        "/api/v1/facturacion/agencias",
        params={"agencia_id": str(cat["agencia_id"]), "size": 100},
        headers=_hdr("cxp"),
    ).json()
    folios = [f["folio_factura_agencia"] for f in lista["items"]]
    assert folios.index("AG-ORDEN-2") < folios.index("AG-ORDEN-1")


def _crear_factura_agencia_simple(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], folio: str = "OC-AG-SIMPLE"
) -> str:
    """Crea su propia `orden_cerrada` (con folio único por llamada, para no chocar si
    se usa varias veces en la misma prueba) y una FacturaAgencia sobre ella."""
    orden_id = _orden(db, cat, "orden_cerrada", folio)
    db.commit()
    r = client.post(
        "/api/v1/facturacion/agencias",
        json={
            "agencia_id": str(cat["agencia_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_agencia": "2026-03-03",
            "monto_factura_agencia": "100.00",
            "iva_factura_agencia": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    return r.json()["factura_agencia_id"]


# ── FacturaVendedor (entidad nueva, paridad con FacturaAgencia) ───────────────────
def test_comision_vendedor_se_calcula_sobre_el_total_de_la_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-VEND")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_vendedor": "2026-03-03",
            "monto_factura_vendedor": "1160.00",
            "iva_factura_vendedor": "185.60",
            "porcentaje_comision_vendedor": "10.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    # OrdenCliente.total = 11600.00 · 10% = 1160.00
    assert r.json()["comision_vendedor"] == "1160.00"
    assert r.json()["total_factura_vendedor"] == "1345.60"


def test_el_porcentaje_de_vendedor_se_sugiere_del_catalogo_si_no_viene(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    vendedor_con_pct_id = uuid.uuid4()
    db.add(
        Vendedor(
            vendedor_id=vendedor_con_pct_id,
            nombre_vendedor="Vendedor Con Default",
            porcentaje_comision_default=Decimal("10.00"),
        )
    )
    orden_id = _orden(
        db, cat, "orden_cerrada", "OC-VEND2", subtotal=Decimal("10000.00")
    )
    db.commit()
    r = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(vendedor_con_pct_id),
            "orden_id": str(orden_id),
            "fecha_factura_vendedor": "2026-03-03",
            "monto_factura_vendedor": "100.00",
            "iva_factura_vendedor": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["porcentaje_comision_vendedor"] == "10.00"  # default del catálogo
    assert r.json()["comision_vendedor"] == "1160.00"


def test_alta_factura_vendedor_trae_vendedor_y_orden_denormalizados(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El alta ya trae `vendedor`/`folio_orden`/`anunciante`/`producto`/`orden_total`
    en la MISMA respuesta (sin esperar al próximo GET) — mismo criterio que
    `_enriquecida()` en `factura_agencia.py`."""
    orden_id = _orden(
        db, cat, "orden_cerrada", "OC-VEND-ENRIQ", producto="Spot radio mayo"
    )
    db.commit()
    r = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_vendedor": "2026-03-03",
            "monto_factura_vendedor": "1160.00",
            "iva_factura_vendedor": "185.60",
            "porcentaje_comision_vendedor": "10.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["vendedor"] == "Vendedor Uno"
    assert body["folio_orden"] == "OC-VEND-ENRIQ"
    assert body["numero_orden_cliente"] == "NUM-OC-VEND-ENRIQ"
    assert body["anunciante"] == "Anunciante Uno"
    assert body["producto"] == "Spot radio mayo"
    assert body["orden_total"] == "11600.00"

    detalle = client.get(
        f"/api/v1/facturacion/vendedores/{body['factura_vendedor_id']}", headers=_hdr("cxp")
    ).json()
    assert detalle["vendedor"] == "Vendedor Uno"
    assert detalle["folio_orden"] == "OC-VEND-ENRIQ"

    lista = client.get(
        "/api/v1/facturacion/vendedores",
        params={"vendedor_id": str(cat["vendedor_id"]), "size": 100},
        headers=_hdr("cxp"),
    ).json()
    en_lista = next(
        f for f in lista["items"] if f["factura_vendedor_id"] == body["factura_vendedor_id"]
    )
    assert en_lista["vendedor"] == "Vendedor Uno"
    assert en_lista["folio_orden"] == "OC-VEND-ENRIQ"


def test_ordenes_facturables_vendedor_solo_lista_las_del_vendedor_principal(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_cerrada = _orden(
        db, cat, "orden_cerrada", "OC-VEND-COMBO", producto="Radio spot"
    )
    _orden(db, cat, "en_transmision", "OC-VEND-NOCERRADA")  # no debe aparecer

    otro_vendedor_id = uuid.uuid4()
    db.add(
        Vendedor(
            vendedor_id=otro_vendedor_id,
            nombre_vendedor="Vendedor Dos",
            porcentaje_comision_default=Decimal("12.50"),
        )
    )
    db.commit()

    r = client.get(
        "/api/v1/facturacion/vendedores/ordenes-facturables",
        params={"vendedor_id": str(cat["vendedor_id"])},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["orden_id"] == str(orden_cerrada)
    assert items[0]["folio_orden"] == "OC-VEND-COMBO"
    assert items[0]["anunciante"] == "Anunciante Uno"
    assert items[0]["producto"] == "Radio spot"
    assert items[0]["total"] == "11600.00"

    # Otro vendedor (no es el principal de ninguna orden) → combo vacío.
    vacio = client.get(
        "/api/v1/facturacion/vendedores/ordenes-facturables",
        params={"vendedor_id": str(otro_vendedor_id)},
        headers=_hdr("cxp"),
    ).json()
    assert vacio == []


def test_editar_factura_vendedor_permite_reasignar_vendedor_y_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La edición hace todo lo que hace el alta — reasignar vendedor y orden
    relacionada, recalculando la comisión contra la NUEVA orden."""
    orden_id = _orden(
        db, cat, "orden_cerrada", "OC-VEND-EDIT-1", subtotal=Decimal("10000.00")
    )
    otro_vendedor_id = uuid.uuid4()
    db.add(
        Vendedor(
            vendedor_id=otro_vendedor_id,
            nombre_vendedor="Vendedor Dos",
            porcentaje_comision_default=Decimal("20.00"),
        )
    )
    db.commit()
    otra_orden_id = _orden(
        db, cat, "orden_cerrada", "OC-VEND-EDIT-2", subtotal=Decimal("5000.00")
    )
    db.commit()

    alta = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_vendedor": "2026-03-03",
            "monto_factura_vendedor": "1160.00",
            "iva_factura_vendedor": "185.60",
            "porcentaje_comision_vendedor": "10.00",
        },
        headers=_hdr("cxp"),
    )
    assert alta.status_code == 201, alta.text
    fid = alta.json()["factura_vendedor_id"]
    # OrdenCliente.total = 5000 * 1.16 = 5800.00 · 20% = 1160.00
    r = client.put(
        f"/api/v1/facturacion/vendedores/{fid}",
        json={
            "vendedor_id": str(otro_vendedor_id),
            "orden_id": str(otra_orden_id),
            "porcentaje_comision_vendedor": "20.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vendedor_id"] == str(otro_vendedor_id)
    assert body["orden_id"] == str(otra_orden_id)
    assert body["vendedor"] == "Vendedor Dos"
    assert body["folio_orden"] == "OC-VEND-EDIT-2"
    assert body["comision_vendedor"] == "1160.00"


def test_editar_factura_vendedor_vendedor_inexistente_400(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_vendedor_simple(client, db, cat, folio="OC-VEND-SIMPLE-1")
    r = client.put(
        f"/api/v1/facturacion/vendedores/{fid}",
        json={"vendedor_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_editar_factura_vendedor_orden_inexistente_400(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_vendedor_simple(client, db, cat, folio="OC-VEND-SIMPLE-2")
    r = client.put(
        f"/api/v1/facturacion/vendedores/{fid}",
        json={"orden_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_editar_factura_vendedor_autorizada_no_permite_reasignar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_vendedor_simple(client, db, cat, folio="OC-VEND-SIMPLE-3")
    client.post(
        f"/api/v1/facturacion/vendedores/{fid}/estatus",
        json={"estatus": "en_revision"},
        headers=_hdr("cxp"),
    )
    client.post(f"/api/v1/facturacion/vendedores/{fid}/autorizar", headers=_hdr("direccion"))

    r = client.put(
        f"/api/v1/facturacion/vendedores/{fid}",
        json={"vendedor_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 409


def test_lista_facturas_vendedor_ordena_por_mas_reciente_primero(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo criterio que FacturaAgencia/FacturaAfiliado: ordena por `created_at`, no
    por `fecha_factura_vendedor` (a propósito invertida respecto al orden de captura)."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-VEND-ORDEN")
    db.commit()

    primera = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "folio_factura_vendedor": "VE-ORDEN-1",
            "fecha_factura_vendedor": "2026-06-01",
            "monto_factura_vendedor": "100.00",
            "iva_factura_vendedor": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert primera.status_code == 201, primera.text

    segunda = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "folio_factura_vendedor": "VE-ORDEN-2",
            "fecha_factura_vendedor": "2026-01-01",
            "monto_factura_vendedor": "100.00",
            "iva_factura_vendedor": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert segunda.status_code == 201, segunda.text

    lista = client.get(
        "/api/v1/facturacion/vendedores",
        params={"vendedor_id": str(cat["vendedor_id"]), "size": 100},
        headers=_hdr("cxp"),
    ).json()
    folios = [f["folio_factura_vendedor"] for f in lista["items"]]
    assert folios.index("VE-ORDEN-2") < folios.index("VE-ORDEN-1")


def test_factura_vendedor_captura_y_edita_archivo_pdf_xml(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-VEND-ARCHIVO")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_vendedor": "2026-03-03",
            "monto_factura_vendedor": "1160.00",
            "iva_factura_vendedor": "185.60",
            "archivo_pdf_path": "facturacion/proveedor/vendedor/pdf/abc_factura.pdf",
            "archivo_xml_path": "facturacion/proveedor/vendedor/xml/abc_factura.xml",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["archivo_pdf_path"] == "facturacion/proveedor/vendedor/pdf/abc_factura.pdf"
    assert r.json()["archivo_xml_path"] == "facturacion/proveedor/vendedor/xml/abc_factura.xml"
    fid = r.json()["factura_vendedor_id"]

    r = client.put(
        f"/api/v1/facturacion/vendedores/{fid}",
        json={"archivo_pdf_path": "facturacion/proveedor/vendedor/pdf/nuevo.pdf"},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["archivo_pdf_path"] == "facturacion/proveedor/vendedor/pdf/nuevo.pdf"
    assert r.json()["archivo_xml_path"] == "facturacion/proveedor/vendedor/xml/abc_factura.xml"


def _crear_factura_vendedor_simple(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID], folio: str = "OC-VEND-SIMPLE"
) -> str:
    """Crea su propia `orden_cerrada` (con folio único por llamada) y una
    FacturaVendedor sobre ella."""
    orden_id = _orden(db, cat, "orden_cerrada", folio)
    db.commit()
    r = client.post(
        "/api/v1/facturacion/vendedores",
        json={
            "vendedor_id": str(cat["vendedor_id"]),
            "orden_id": str(orden_id),
            "fecha_factura_vendedor": "2026-03-03",
            "monto_factura_vendedor": "100.00",
            "iva_factura_vendedor": "16.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    return r.json()["factura_vendedor_id"]


# ── CostoAdicional ────────────────────────────────────────────────────────────
def test_costo_general_sin_orden_y_periodo_invalido(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/facturacion/costos",
        json={
            "tipo_costo": "nomina",
            "descripcion_costo": "Nómina febrero",
            "periodo_contable": "2026-02",
            "monto_costo": "50000.00",
        },
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201
    assert r.json()["orden_id"] is None

    # El formato fino (dígitos y mes 01-12) lo valida Pydantic, no el CHECK (ADR-045).
    for periodo in ("feb-2026", "2026-13", "2026-2"):
        r = client.post(
            "/api/v1/facturacion/costos",
            json={
                "tipo_costo": "overhead",
                "descripcion_costo": "X",
                "periodo_contable": periodo,
                "monto_costo": "1.00",
            },
            headers=_hdr("cxp"),
        )
        assert r.status_code == 422, periodo


# ── Bandeja "Listas para facturar" ────────────────────────────────────────────
def test_bandeja_lista_ordenes_cerradas_sin_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El corazón de la bandeja: `LEFT JOIN` + `IS NULL`."""
    cerrada_sin_factura = _orden(db, cat, "orden_cerrada", "OC-SIN-FACTURA")
    _orden(db, cat, "en_verificacion", "OC-NO-CERRADA")  # no cerrada: no debe aparecer
    db.commit()

    r = client.get("/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion"))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 1
    fila = cuerpo["items"][0]
    assert fila["orden_id"] == str(cerrada_sin_factura)
    assert fila["folio_orden"] == "OC-SIN-FACTURA"
    # anunciante_id viaja además del nombre (ADR-062): la pantalla lo necesita para
    # filtrar el combo de "Factura relacionada" por anunciante.
    assert fila["anunciante_id"] == str(cat["anunciante_id"])
    # Los nombres vienen resueltos por el JOIN, no como IDs.
    assert fila["anunciante"] == "Anunciante Uno"
    assert fila["agencia"] == "Agencia Uno"
    assert fila["vendedor"] == "Vendedor Uno"
    assert fila["total"] == "11600.00"


def test_al_facturar_la_orden_sale_de_la_bandeja(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _crear_factura(client, db, cat, "F-9015")
    r = client.get("/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion"))
    assert r.json()["total"] == 0


def test_una_orden_sin_agencia_aparece_con_agencia_nula(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Trato directo: el `outerjoin` no debe eliminar la fila (sería un INNER silencioso)."""
    from app.modules.ordenes.orden_cliente import OrdenCliente

    orden_id = _orden(db, cat, "orden_cerrada", "OC-DIRECTA")
    oc = db.get(OrdenCliente, orden_id)
    assert oc is not None
    oc.agencia_id = None
    db.commit()

    r = client.get("/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion"))
    filas = [f for f in r.json()["items"] if f["orden_id"] == str(orden_id)]
    assert len(filas) == 1
    assert filas[0]["agencia"] is None


def test_la_bandeja_exige_permiso_de_facturacion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    assert (
        client.get("/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("ventas")).status_code
        == 200  # Ventas LEE facturación (matriz de la ficha)
    )
    assert (
        client.get(
            "/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("marketing")
        ).status_code
        in (401, 403, 422)
    )


# ── Tanda 4: cancelar revierte el handoff (ADR-047) ───────────────────────────
def _timbrar(client: TestClient, factura_id: str) -> None:
    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado", headers=_hdr("facturacion")
    )
    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "FOLIO-1", "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 200, r.text


def test_cancelar_una_timbrada_regresa_la_orden_a_cerrada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id = _crear_factura(client, db, cat, "F-9016")
    _timbrar(client, factura_id)
    db.expire_all()
    assert db.get(OrdenCliente, orden_id).estatus_orden == "facturada"

    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    assert r.json()["estado_facturacion"] == "cancelada"

    db.expire_all()
    assert db.get(OrdenCliente, orden_id).estatus_orden == "orden_cerrada"


def test_tras_cancelar_se_puede_facturar_de_nuevo_la_misma_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Lo que habilita el índice único FILTRADO: la cancelada no bloquea a la nueva."""
    factura_id, orden_id = _crear_factura(client, db, cat, "F-1")
    _timbrar(client, factura_id)
    client.post(f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion"))

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-2"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["estado_facturacion"] == "preparada"

    # Y la SEGUNDA vigente sí vuelve a bloquear una tercera.
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-3"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409


def test_la_factura_cancelada_no_se_borra_y_sigue_listandose(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    factura_id, orden_id = _crear_factura(client, db, cat, "F-9017")
    _timbrar(client, factura_id)
    client.post(f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion"))
    client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-9018"),
        headers=_hdr("facturacion"),
    )

    r = client.get(
        "/api/v1/facturacion/clientes",
        params={"orden_id": str(orden_id)},
        headers=_hdr("facturacion"),
    )
    numeros = {f["numero_factura"]: f["estado_facturacion"] for f in r.json()["items"]}
    assert numeros == {"F-9017": "cancelada", "F-9018": "preparada"}

    # Y sigue apareciendo bajo su propio filtro de estado.
    r = client.get(
        "/api/v1/facturacion/clientes",
        params={"estado_facturacion": "cancelada"},
        headers=_hdr("facturacion"),
    )
    assert r.json()["total"] == 1


def test_no_se_cancela_la_factura_de_una_orden_ya_cobrada(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Requeriría una nota de crédito real, fuera del alcance de F2."""
    factura_id, orden_id = _crear_factura(client, db, cat, "F-9019")
    _timbrar(client, factura_id)
    oc = db.get(OrdenCliente, orden_id)
    assert oc is not None
    oc.estatus_orden = "cobrada"  # lo hará F3
    db.commit()

    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion")
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"

    # Ni la factura ni la orden se movieron.
    db.rollback()
    db.expire_all()
    assert db.get(FacturaCliente, uuid.UUID(factura_id)).estado_facturacion == "timbrada"
    assert db.get(OrdenCliente, orden_id).estatus_orden == "cobrada"


def test_cancelar_desde_preparada_no_toca_la_orden(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El handoff nunca ocurrió (se dispara al TIMBRAR): no hay nada que revertir."""
    factura_id, orden_id = _crear_factura(client, db, cat, "F-9020")
    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    db.expire_all()
    assert db.get(OrdenCliente, orden_id).estatus_orden == "orden_cerrada"


def test_la_orden_reaparece_en_la_bandeja_tras_cancelar(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Sin el filtro de canceladas en el JOIN, sería re-facturable pero invisible."""
    factura_id, orden_id = _crear_factura(client, db, cat, "F-9021")
    assert client.get(
        "/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion")
    ).json()["total"] == 0

    _timbrar(client, factura_id)
    client.post(f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion"))

    cuerpo = client.get(
        "/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion")
    ).json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["orden_id"] == str(orden_id)


# ── Facturación múltiple: una factura sobre VARIAS órdenes (ADR-064) ──────────
def test_alta_con_varias_ordenes_suma_subtotales_y_abarca_el_periodo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El subtotal es la SUMA de subtotales y el periodo abarca de la más temprana a la
    más tardía. El IVA se recalcula sobre la suma, no se suman IVAs ya redondeados."""
    a = _orden(
        db, cat, "orden_cerrada", "OC-M1",
        subtotal=Decimal("10000.00"), inicio=date(2026, 2, 1), fin=date(2026, 2, 15),
    )
    b = _orden(
        db, cat, "orden_cerrada", "OC-M2",
        subtotal=Decimal("5000.50"), inicio=date(2026, 1, 20), fin=date(2026, 3, 10),
    )
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, b], cat["cuenta_id"], "F-9022"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert Decimal(cuerpo["subtotal_factura"]) == Decimal("15000.50")
    assert Decimal(cuerpo["iva_factura"]) == Decimal("2400.08")
    assert Decimal(cuerpo["total_factura"]) == Decimal("17400.58")
    # El periodo va del inicio más temprano al fin más tardío, no del de la primera orden.
    assert cuerpo["fecha_inicio_transmision"] == "2026-01-20"
    assert cuerpo["fecha_fin_transmision"] == "2026-03-10"
    assert [o["folio_orden"] for o in cuerpo["ordenes"]] == ["OC-M1", "OC-M2"]


def test_alta_rechaza_ordenes_de_distinta_empresa_facturadora(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Un CFDI tiene UN emisor: no se pueden mezclar emisoras."""
    otra_empresa = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=otra_empresa,
            nombre_empresa="Otra Emisora SA",
            rfc_empresa="OEM900101AB1",
        )
    )
    db.flush()
    a = _orden(db, cat, "orden_cerrada", "OC-E1")
    b = _orden(db, cat, "orden_cerrada", "OC-E2", empresa_id=otra_empresa)
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, b], cat["cuenta_id"], "F-9023"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 400
    assert "misma empresa facturadora" in r.json()["error"]["mensaje"]


def test_alta_rechaza_mezclar_receptor_agencia_con_directo(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo anunciante y misma agencia, pero una se factura directo: el receptor difiere.

    Es el caso que `agencia_id` por sí solo NO detecta — por eso el receptor se compara
    como par (tipo, id) y no por la columna.
    """
    a = _orden(db, cat, "orden_cerrada", "OC-R1", directa=False)
    b = _orden(db, cat, "orden_cerrada", "OC-R2", directa=True)
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, b], cat["cuenta_id"], "F-9024"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 400
    assert "mismo receptor" in r.json()["error"]["mensaje"]


def test_alta_reporta_todas_las_ordenes_no_cerradas_no_solo_la_primera(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Con varias marcadas, corregirlas de una en una sería exasperante."""
    ok = _orden(db, cat, "orden_cerrada", "OC-OK")
    mala1 = _orden(db, cat, "en_verificacion", "OC-MALA1")
    mala2 = _orden(db, cat, "capturada", "OC-MALA2")
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([ok, mala1, mala2], cat["cuenta_id"], "F-9025"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 400
    folios = {o["folio_orden"] for o in r.json()["error"]["detalles"]["ordenes"]}
    assert folios == {"OC-MALA1", "OC-MALA2"}


def test_alta_rechaza_si_alguna_orden_ya_tiene_factura_vigente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """409 nombrando la orden y la factura que la ocupa."""
    ocupada = _orden(db, cat, "orden_cerrada", "OC-OCUPADA")
    db.commit()
    primera = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(ocupada, cat["cuenta_id"], "F-9026"),
        headers=_hdr("facturacion"),
    )
    assert primera.status_code == 201

    libre = _orden(db, cat, "orden_cerrada", "OC-LIBRE")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([libre, ocupada], cat["cuenta_id"], "F-9027"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409
    detalle = r.json()["error"]["detalles"]["ordenes"]
    assert detalle == [{"folio_orden": "OC-OCUPADA", "numero_factura": "F-9026"}]


def test_alta_deduplica_la_misma_orden_repetida(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mandar dos veces la misma orden no la cobra dos veces ni rompe la PK compuesta."""
    a = _orden(db, cat, "orden_cerrada", "OC-DUP", subtotal=Decimal("10000.00"))
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, a], cat["cuenta_id"], "F-9028"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["subtotal_factura"]) == Decimal("10000.00")
    assert len(r.json()["ordenes"]) == 1


def test_timbrar_y_cancelar_mueven_todas_las_ordenes(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El handoff con F1 recorre las N órdenes, en los dos sentidos."""
    a = _orden(db, cat, "orden_cerrada", "OC-H1")
    b = _orden(db, cat, "orden_cerrada", "OC-H2")
    db.commit()
    factura_id = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, b], cat["cuenta_id"], "F-9029"),
        headers=_hdr("facturacion"),
    ).json()["factura_id"]

    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/enviar-a-timbrado",
        headers=_hdr("facturacion"),
    )
    r = client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/timbrar",
        json={"folio_fiscal_sat": "F" * 36, "fecha_timbrado": "2026-03-02"},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert [db.get(OrdenCliente, o).estatus_orden for o in (a, b)] == ["facturada"] * 2

    client.post(
        f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion")
    )
    db.expire_all()
    assert [db.get(OrdenCliente, o).estatus_orden for o in (a, b)] == ["orden_cerrada"] * 2


def test_el_archivo_plano_consolida_los_folios_de_todas_las_ordenes(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Decisión del equipo: UNA línea de detalle, con los campos de campaña concatenados."""
    a = _orden(db, cat, "orden_cerrada", "OC-P1", producto="SPOT RADIO")
    b = _orden(db, cat, "orden_cerrada", "OC-P2", producto="SPOT RADIO")
    db.commit()
    factura_id = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, b], cat["cuenta_id"], "F-9030"),
        headers=_hdr("facturacion"),
    ).json()["factura_id"]

    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    texto = r.content.decode("cp1252")
    assert "OC-P1, OC-P2" in texto
    assert "NUM-OC-P1, NUM-OC-P2" in texto
    # Producto común: se emite tal cual, no la descripción de la factura.
    assert "SPOT RADIO" in texto
    # Una sola línea de detalle pese a ser dos órdenes: cabecera + 1 fila.
    detalle = texto.split("================ Detalle")[1].split("XXXFINDETA")[0]
    assert len([ln for ln in detalle.split("\r\n") if ln.strip()]) == 2


def test_el_archivo_plano_cae_a_la_descripcion_si_los_productos_difieren(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Inventar una campaña común sería peor que usar lo que capturó Facturación."""
    a = _orden(db, cat, "orden_cerrada", "OC-Q1", producto="SPOT RADIO")
    b = _orden(db, cat, "orden_cerrada", "OC-Q2", producto="MENCION EN VIVO")
    db.commit()
    factura_id = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, b], cat["cuenta_id"], "F-9031"),
        headers=_hdr("facturacion"),
    ).json()["factura_id"]

    r = client.get(
        f"/api/v1/facturacion/clientes/{factura_id}/archivo-plano", headers=_hdr("facturacion")
    )
    texto = r.content.decode("cp1252")
    assert "Servicios de transmisión febrero 2026" in texto


def test_la_bandeja_se_filtra_por_anunciante(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    otro_anunciante = uuid.uuid4()
    db.add(
        Anunciante(
            anunciante_id=otro_anunciante,
            nombre_comercial="Otro Anunciante",
            nombre_fiscal="Otro Anunciante SA",
            rfc_anunciante="OAN900101AB1",
        )
    )
    db.flush()
    _orden(db, cat, "orden_cerrada", "OC-A1")
    _orden(db, cat, "orden_cerrada", "OC-A2")
    _orden(db, cat, "orden_cerrada", "OC-B1", anunciante_id=otro_anunciante)
    db.commit()

    r = client.get(
        "/api/v1/facturacion/ordenes-por-facturar",
        params={"anunciante_id": str(otro_anunciante)},
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 200
    assert [o["folio_orden"] for o in r.json()["items"]] == ["OC-B1"]


def test_el_combo_de_anunciantes_exige_permiso_de_facturacion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo RBAC que la bandeja de la que cuelga: no basta con que el dato sea inocuo."""
    ruta = "/api/v1/facturacion/ordenes-por-facturar/anunciantes"
    assert client.get(ruta, headers=_hdr("ventas")).status_code == 200
    assert client.get(ruta, headers=_hdr("marketing")).status_code in (401, 403, 422)


def test_el_combo_solo_ofrece_anunciantes_con_dos_o_mas_ordenes_disponibles(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Con una sola orden no hay nada que agrupar; y las ya facturadas no cuentan."""
    a = _orden(db, cat, "orden_cerrada", "OC-C1")
    _orden(db, cat, "orden_cerrada", "OC-C2")
    db.commit()

    r = client.get(
        "/api/v1/facturacion/ordenes-por-facturar/anunciantes", headers=_hdr("facturacion")
    )
    assert r.status_code == 200
    combos = [(x["anunciante"], x["ordenes"]) for x in r.json()]
    assert len(combos) == 1 and combos[0][1] == 2

    # Al facturar una de las dos, el anunciante baja a 1 disponible y sale del combo.
    client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(a, cat["cuenta_id"], "F-9032"),
        headers=_hdr("facturacion"),
    )
    r2 = client.get(
        "/api/v1/facturacion/ordenes-por-facturar/anunciantes", headers=_hdr("facturacion")
    )
    assert r2.json() == []


def test_una_orden_con_facturas_canceladas_y_una_vigente_no_vuelve_a_la_bandeja(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Regresión: la bandeja preguntaba por EXISTENCIA con LEFT JOIN, y eso multiplicaba.

    Con la relación N:M, un LEFT JOIN a la puente produce una fila por cada factura de la
    orden. Las canceladas no casan con la condición del join a `factura_cliente`, así que
    dejaban su fila con la factura en NULL y la orden pasaba el filtro "sin factura" —
    apareciendo en la bandeja UNA VEZ POR CANCELADA, aunque tuviera su factura vigente.
    """
    orden = _orden(db, cat, "orden_cerrada", "OC-ZOMBI")
    db.commit()

    # Dos facturas canceladas sobre la misma orden...
    for numero in ("F-9036", "F-9037"):
        fid = client.post(
            "/api/v1/facturacion/clientes",
            json=_payload_factura(orden, cat["cuenta_id"], numero),
            headers=_hdr("facturacion"),
        ).json()["factura_id"]
        client.post(
            f"/api/v1/facturacion/clientes/{fid}/cancelar", headers=_hdr("facturacion")
        )

    # ...y ahora sí, una vigente.
    assert (
        client.post(
            "/api/v1/facturacion/clientes",
            json=_payload_factura(orden, cat["cuenta_id"], "F-9033"),
            headers=_hdr("facturacion"),
        ).status_code
        == 201
    )

    bandeja = client.get(
        "/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion")
    ).json()
    folios = [o["folio_orden"] for o in bandeja["items"]]
    assert "OC-ZOMBI" not in folios, "una orden ya facturada reapareció en la bandeja"
    assert bandeja["total"] == 0


def test_el_combo_no_cuenta_dos_veces_una_orden_con_varias_canceladas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """El mismo defecto inflaba el conteo del combo: contaba filas, no órdenes."""
    a = _orden(db, cat, "orden_cerrada", "OC-N1")
    _orden(db, cat, "orden_cerrada", "OC-N2")
    db.commit()

    fid = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(a, cat["cuenta_id"], "F-9034"),
        headers=_hdr("facturacion"),
    ).json()["factura_id"]
    client.post(f"/api/v1/facturacion/clientes/{fid}/cancelar", headers=_hdr("facturacion"))

    combo = client.get(
        "/api/v1/facturacion/ordenes-por-facturar/anunciantes", headers=_hdr("facturacion")
    ).json()
    # La orden cancelada vuelve a estar disponible: son 2 órdenes, no 3 filas.
    assert [x["ordenes"] for x in combo] == [2]


def test_una_orden_con_su_factura_cancelada_vuelve_a_la_bandeja(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La otra mitad de ADR-047, para que el arreglo anterior no se pase de estricto."""
    orden = _orden(db, cat, "orden_cerrada", "OC-VUELVE")
    db.commit()
    fid = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden, cat["cuenta_id"], "F-9035"),
        headers=_hdr("facturacion"),
    ).json()["factura_id"]

    despues_de_facturar = client.get(
        "/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion")
    ).json()
    assert "OC-VUELVE" not in [o["folio_orden"] for o in despues_de_facturar["items"]]

    client.post(f"/api/v1/facturacion/clientes/{fid}/cancelar", headers=_hdr("facturacion"))
    despues_de_cancelar = client.get(
        "/api/v1/facturacion/ordenes-por-facturar", headers=_hdr("facturacion")
    ).json()
    assert [o["folio_orden"] for o in despues_de_cancelar["items"]] == ["OC-VUELVE"]


# ── FacturaAfiliado: combo "Folio de la Orden Interna" + auto-asignación ──────────
def _payload_factura_afiliado(cat: dict[str, uuid.UUID], **overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        afiliado_id=str(cat["afiliado_id"]),
        factura_emisora="EMI-TEST-001",
        fecha_factura_afiliado="2026-04-10",
        monto_factura_afiliado="7000.00",
        iva_factura_afiliado="1120.00",
    )
    base.update(overrides)
    return base


def test_ordenes_facturables_afiliado_solo_lista_las_cerradas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-COMBO")
    oe_cerrada = _orden_estacion(db, cat, orden_id, "cerrada")
    _orden_estacion(db, cat, orden_id, "asignada")  # no debe aparecer en el combo
    db.commit()

    r = client.get(
        "/api/v1/facturacion/afiliados/ordenes-facturables",
        params={"afiliado_id": str(cat["afiliado_id"])},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["orden_estacion_id"] == str(oe_cerrada)
    assert items[0]["importe_emisora"] == "7000.00"
    assert items[0]["iva_emisora"] == "1120.00"
    assert items[0]["total_emisora"] == "8120.00"


def test_crear_factura_afiliado_con_orden_estacion_asigna_automaticamente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-AUTO")
    oe = _orden_estacion(db, cat, orden_id, "cerrada")
    db.commit()

    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat, ordenes_estacion_ids=[str(oe)]),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    factura_id = r.json()["factura_afiliado_id"]

    asignaciones = client.get(
        f"/api/v1/facturacion/afiliados/{factura_id}/ordenes", headers=_hdr("cxp")
    ).json()
    assert len(asignaciones) == 1
    assert asignaciones[0]["orden_estacion_id"] == str(oe)
    # El monto asignado es el importe_emisora de la propia OE (fijo en `_orden_estacion`
    # en $7,000.00), no una repartición del subtotal capturado en la factura.
    assert asignaciones[0]["monto_asignado"] == "7000.00"
    # Folio y estación resueltos por el servicio (no el UUID crudo de la OE): la
    # pantalla los necesita para no mostrar un identificador ilegible.
    oe_db = db.get(OrdenEstacion, oe)
    assert asignaciones[0]["folio_orden_estacion"] == oe_db.folio_orden_estacion
    assert asignaciones[0]["nombre_estacion"] == "XHTEST-FM"


def test_crear_factura_afiliado_orden_estacion_no_cerrada_400(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-NOCERRADA")
    oe = _orden_estacion(db, cat, orden_id, "asignada")
    db.commit()

    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat, ordenes_estacion_ids=[str(oe)]),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_crear_factura_afiliado_orden_estacion_inexistente_400(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat, ordenes_estacion_ids=[str(uuid.uuid4())]),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_crear_factura_afiliado_sin_orden_estacion_no_crea_asignacion(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    """El combo es opcional: una factura de afiliado se sigue pudiendo capturar sin
    ligarla a ninguna OI en el alta (se asigna después, a mano, con "+ Asignar OE")."""
    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    factura_id = r.json()["factura_afiliado_id"]

    asignaciones = client.get(
        f"/api/v1/facturacion/afiliados/{factura_id}/ordenes", headers=_hdr("cxp")
    ).json()
    assert asignaciones == []


def test_crear_factura_afiliado_permite_facturar_la_misma_oe_en_parcialidades(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """La spec permite facturar una OE en parcialidades (ver
    `FacturaAfiliadoOrden.__table_args__`): dos facturas DISTINTAS pueden asignarse a la
    MISMA OrdenEstacion sin que la segunda alta se rechace."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-PARCIAL")
    oe = _orden_estacion(db, cat, orden_id, "cerrada")
    db.commit()

    for numero in ("EMI-PARCIAL-1", "EMI-PARCIAL-2"):
        r = client.post(
            "/api/v1/facturacion/afiliados",
            json=_payload_factura_afiliado(
                cat,
                factura_emisora=numero,
                monto_factura_afiliado="3500.00",
                iva_factura_afiliado="560.00",
                ordenes_estacion_ids=[str(oe)],
            ),
            headers=_hdr("cxp"),
        )
        assert r.status_code == 201, r.text


def test_crear_factura_afiliado_con_varias_ordenes_estacion_asigna_cada_una(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Selecciona más de una OI en el alta: se crea una asignación por cada una, cada
    una con SU PROPIO importe_emisora (no una repartición del subtotal capturado)."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-MULTI")
    # Mismo criterio 70/30 (emisora/OIR) que el default del helper, con montos reales
    # distintos por OE — importe_estacion = importe_oir + importe_emisora (CHECK).
    oe_a = _orden_estacion(
        db,
        cat,
        orden_id,
        "cerrada",
        importe_estacion=Decimal("408000.00"),
        importe_oir=Decimal("122400.00"),
        iva_oir=Decimal("19584.00"),
        total_oir=Decimal("141984.00"),
        importe_emisora=Decimal("285600.00"),
        iva_emisora=Decimal("45696.00"),
        total_emisora=Decimal("331296.00"),
    )
    oe_b = _orden_estacion(
        db,
        cat,
        orden_id,
        "cerrada",
        importe_estacion=Decimal("240000.00"),
        importe_oir=Decimal("72000.00"),
        iva_oir=Decimal("11520.00"),
        total_oir=Decimal("83520.00"),
        importe_emisora=Decimal("168000.00"),
        iva_emisora=Decimal("26880.00"),
        total_emisora=Decimal("194880.00"),
    )
    db.commit()

    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(
            cat,
            monto_factura_afiliado="453600.00",
            iva_factura_afiliado="72576.00",
            ordenes_estacion_ids=[str(oe_a), str(oe_b)],
        ),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    # El conteo ya viene correcto en la MISMA respuesta del alta, sin esperar al
    # próximo GET (mismo criterio que `_enriquecida` en `factura_cliente.py`).
    assert r.json()["ordenes_asignadas"] == 2
    factura_id = r.json()["factura_afiliado_id"]

    asignaciones = client.get(
        f"/api/v1/facturacion/afiliados/{factura_id}/ordenes", headers=_hdr("cxp")
    ).json()
    por_oe = {a["orden_estacion_id"]: a["monto_asignado"] for a in asignaciones}
    assert por_oe == {str(oe_a): "285600.00", str(oe_b): "168000.00"}

    # Columna "OE Asig." de la lista: se resuelve en lote, sin que el front tenga que
    # pedir `/ordenes` de cada factura para saber cuántas trae.
    detalle = client.get(
        f"/api/v1/facturacion/afiliados/{factura_id}", headers=_hdr("cxp")
    ).json()
    assert detalle["ordenes_asignadas"] == 2

    lista = client.get(
        "/api/v1/facturacion/afiliados",
        params={"afiliado_id": str(cat["afiliado_id"]), "size": 100},
        headers=_hdr("cxp"),
    ).json()
    en_lista = next(f for f in lista["items"] if f["factura_afiliado_id"] == factura_id)
    assert en_lista["ordenes_asignadas"] == 2


def test_factura_afiliado_sin_ordenes_asignadas_muestra_conteo_cero(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["ordenes_asignadas"] == 0

    factura_id = r.json()["factura_afiliado_id"]
    detalle = client.get(
        f"/api/v1/facturacion/afiliados/{factura_id}", headers=_hdr("cxp")
    ).json()
    assert detalle["ordenes_asignadas"] == 0


def test_crear_factura_afiliado_rechaza_la_misma_oe_repetida_en_el_alta(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REPETIDA")
    oe = _orden_estacion(db, cat, orden_id, "cerrada")
    db.commit()

    r = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat, ordenes_estacion_ids=[str(oe), str(oe)]),
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_lista_facturas_afiliado_ordena_por_mas_reciente_primero(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: al capturar una factura nueva, siempre sube hasta arriba
    de la lista — sin importar `fecha_factura_afiliado` (que puede ser una fecha
    pasada), se ordena por el momento REAL del alta (`created_at`)."""
    primera = client.post(
        "/api/v1/facturacion/afiliados",
        # Fecha de factura más reciente que la segunda, a propósito: si se ordenara
        # por `fecha_factura_afiliado` en vez de `created_at`, esta quedaría arriba.
        json=_payload_factura_afiliado(
            cat, factura_emisora="EMI-ORDEN-1", fecha_factura_afiliado="2026-06-01"
        ),
        headers=_hdr("cxp"),
    )
    assert primera.status_code == 201, primera.text

    segunda = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(
            cat, factura_emisora="EMI-ORDEN-2", fecha_factura_afiliado="2026-01-01"
        ),
        headers=_hdr("cxp"),
    )
    assert segunda.status_code == 201, segunda.text

    lista = client.get(
        "/api/v1/facturacion/afiliados",
        params={"afiliado_id": str(cat["afiliado_id"]), "size": 100},
        headers=_hdr("cxp"),
    ).json()
    folios = [f["factura_emisora"] for f in lista["items"]]
    assert folios.index("EMI-ORDEN-2") < folios.index("EMI-ORDEN-1")


# ── Editar FacturaAfiliado: hace todo lo que hace el alta ─────────────────────────
def test_editar_factura_afiliado_permite_reasignar_afiliado(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Petición del usuario: la edición ya no deja el afiliado fijo — se re-deriva
    `razon_social_afiliada` del NUEVO afiliado, igual que en el alta."""
    otro_afiliado_id = uuid.uuid4()
    db.add(
        Afiliado(
            afiliado_id=otro_afiliado_id,
            nombre_afiliado="Afiliado Dos",
            razon_social_afiliado="Afiliado Dos SA de CV",
            rfc_afiliado="ADS900101AB2",
            plaza_id=cat["plaza_id"],
        )
    )
    db.commit()

    fid = _crear_factura_afiliado(client, cat)
    r = client.put(
        f"/api/v1/facturacion/afiliados/{fid}",
        json={"afiliado_id": str(otro_afiliado_id)},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["afiliado_id"] == str(otro_afiliado_id)
    assert r.json()["razon_social_afiliada"] == "Afiliado Dos SA de CV"


def test_editar_factura_afiliado_afiliado_inexistente_400(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_afiliado(client, cat)
    r = client.put(
        f"/api/v1/facturacion/afiliados/{fid}",
        json={"afiliado_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"


def test_editar_factura_afiliado_reconcilia_ordenes_estacion(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """`ordenes_estacion_ids` en la edición deja las asignaciones EXACTAMENTE como pide
    la lista: agrega las nuevas, quita las que ya no están, y las que siguen (oe_b) se
    quedan con su `monto_asignado` intacto."""
    orden_id = _orden(db, cat, "orden_cerrada", "OC-EDITAR-OE")
    # importe_estacion = importe_oir + importe_emisora (CHECK
    # `ck_orden_estacion_margen_oir_emisora`) — mismo criterio 70/30 que otros tests.
    oe_a = _orden_estacion(
        db,
        cat,
        orden_id,
        "cerrada",
        importe_estacion=Decimal("1300.00"),
        importe_oir=Decimal("300.00"),
        iva_oir=Decimal("48.00"),
        total_oir=Decimal("348.00"),
        importe_emisora=Decimal("1000.00"),
        iva_emisora=Decimal("160.00"),
        total_emisora=Decimal("1160.00"),
    )
    oe_b = _orden_estacion(
        db,
        cat,
        orden_id,
        "cerrada",
        importe_estacion=Decimal("2600.00"),
        importe_oir=Decimal("600.00"),
        iva_oir=Decimal("96.00"),
        total_oir=Decimal("696.00"),
        importe_emisora=Decimal("2000.00"),
        iva_emisora=Decimal("320.00"),
        total_emisora=Decimal("2320.00"),
    )
    oe_c = _orden_estacion(
        db,
        cat,
        orden_id,
        "cerrada",
        importe_estacion=Decimal("3900.00"),
        importe_oir=Decimal("900.00"),
        iva_oir=Decimal("144.00"),
        total_oir=Decimal("1044.00"),
        importe_emisora=Decimal("3000.00"),
        iva_emisora=Decimal("480.00"),
        total_emisora=Decimal("3480.00"),
    )
    db.commit()

    alta = client.post(
        "/api/v1/facturacion/afiliados",
        json=_payload_factura_afiliado(cat, ordenes_estacion_ids=[str(oe_a), str(oe_b)]),
        headers=_hdr("cxp"),
    )
    assert alta.status_code == 201, alta.text
    fid = alta.json()["factura_afiliado_id"]

    r = client.put(
        f"/api/v1/facturacion/afiliados/{fid}",
        json={"ordenes_estacion_ids": [str(oe_b), str(oe_c)]},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ordenes_asignadas"] == 2

    asignaciones = client.get(
        f"/api/v1/facturacion/afiliados/{fid}/ordenes", headers=_hdr("cxp")
    ).json()
    por_oe = {a["orden_estacion_id"]: a["monto_asignado"] for a in asignaciones}
    # oe_a se quitó, oe_c se agregó con su propio importe_emisora, y oe_b (que ya
    # estaba) se queda con el mismo monto de antes.
    assert por_oe == {str(oe_b): "2000.00", str(oe_c): "3000.00"}


def test_editar_factura_afiliado_orden_estacion_no_cerrada_400(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    fid = _crear_factura_afiliado(client, cat)
    orden_id = _orden(db, cat, "en_transmision", "OC-EDITAR-NOCERRADA")
    oe = _orden_estacion(db, cat, orden_id, "en_transmision")
    db.commit()

    r = client.put(
        f"/api/v1/facturacion/afiliados/{fid}",
        json={"ordenes_estacion_ids": [str(oe)]},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "error_dominio"

    # La validación falla ANTES de tocar nada: sin asignaciones a medias.
    asignaciones = client.get(
        f"/api/v1/facturacion/afiliados/{fid}/ordenes", headers=_hdr("cxp")
    ).json()
    assert asignaciones == []


def test_editar_factura_afiliado_autorizada_no_permite_reasignar_ni_reconciliar(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo candado que ya protege monto/IVA (`Una factura autorizada o pagada ya no
    se edita`): también aplica a `afiliado_id`/`ordenes_estacion_ids`."""
    fid = _crear_factura_afiliado(client, cat)
    client.post(
        f"/api/v1/facturacion/afiliados/{fid}/estatus",
        json={"estatus": "en_revision"},
        headers=_hdr("cxp"),
    )
    client.post(f"/api/v1/facturacion/afiliados/{fid}/autorizar", headers=_hdr("direccion"))

    r = client.put(
        f"/api/v1/facturacion/afiliados/{fid}",
        json={"afiliado_id": str(uuid.uuid4())},
        headers=_hdr("cxp"),
    )
    assert r.status_code == 409
