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


def _orden_estacion(
    db: Session, cat: dict[str, uuid.UUID], orden_id: uuid.UUID, estatus: str
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
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-X"),
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
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-CONFOLIO"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["folio_orden"] == "OC-CONFOLIO"


def test_no_se_aceptan_campos_calculados_del_cliente(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    orden_id = _orden(db, cat, "orden_cerrada", "OC-FORBID")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-FORBID")
    payload["total_factura"] = "1.00"  # calculado: el schema debe rechazarlo
    r = client.post("/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion"))
    assert r.status_code == 422


def test_una_orden_solo_admite_una_factura(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    _, orden_id = _crear_factura(client, db, cat)
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-DUP"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "conflicto"


# ── Facturas relacionadas (N:N, ADR-062) ───────────────────────────────────────
def test_alta_admite_varias_facturas_relacionadas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    id_a, _ = _crear_factura(client, db, cat, "F-REL-A")
    id_b, _ = _crear_factura(client, db, cat, "F-REL-B")
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-C")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-REL-C")
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
    id_a, _ = _crear_factura(client, db, cat, "F-REL-DUP-A")
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-DUP-B")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-REL-DUP-B")
    payload["facturas_relacionadas_ids"] = [id_a, id_a]
    r = client.post("/api/v1/facturacion/clientes", json=payload, headers=_hdr("facturacion"))
    assert r.status_code == 201, r.text
    assert r.json()["facturas_relacionadas_ids"] == [id_a]


def test_las_transiciones_no_pierden_las_facturas_relacionadas(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mismo bug que ADR-055 resolvió para `folio_orden`: la respuesta de una transición
    debe traer `facturas_relacionadas_ids` ya resuelto, no vacío hasta el próximo GET."""
    id_a, _ = _crear_factura(client, db, cat, "F-REL-TRANS-A")
    orden_id = _orden(db, cat, "orden_cerrada", "OC-REL-TRANS-B")
    db.commit()
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-REL-TRANS-B")
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
    payload = _payload_factura(orden_id, cat["cuenta_id"], "F-REL-404")
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
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-DIRECTA"),
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
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-CRUCE"),
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
    _crear_factura(client, db, cat, "F-BANDEJA")
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
    factura_id, orden_id = _crear_factura(client, db, cat, "F-REV")
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
    factura_id, orden_id = _crear_factura(client, db, cat, "F-HIST")
    _timbrar(client, factura_id)
    client.post(f"/api/v1/facturacion/clientes/{factura_id}/cancelar", headers=_hdr("facturacion"))
    client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura(orden_id, cat["cuenta_id"], "F-HIST-2"),
        headers=_hdr("facturacion"),
    )

    r = client.get(
        "/api/v1/facturacion/clientes",
        params={"orden_id": str(orden_id)},
        headers=_hdr("facturacion"),
    )
    numeros = {f["numero_factura"]: f["estado_facturacion"] for f in r.json()["items"]}
    assert numeros == {"F-HIST": "cancelada", "F-HIST-2": "preparada"}

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
    factura_id, orden_id = _crear_factura(client, db, cat, "F-COB")
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
    factura_id, orden_id = _crear_factura(client, db, cat, "F-PREP")
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
    factura_id, orden_id = _crear_factura(client, db, cat, "F-BAND")
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
        json=_payload_factura([a, b], cat["cuenta_id"], "F-MULTI"),
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
        json=_payload_factura([a, b], cat["cuenta_id"], "F-EMI"),
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
        json=_payload_factura([a, b], cat["cuenta_id"], "F-REC"),
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
        json=_payload_factura([ok, mala1, mala2], cat["cuenta_id"], "F-NC"),
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
        json=_payload_factura(ocupada, cat["cuenta_id"], "F-PRIM"),
        headers=_hdr("facturacion"),
    )
    assert primera.status_code == 201

    libre = _orden(db, cat, "orden_cerrada", "OC-LIBRE")
    db.commit()
    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([libre, ocupada], cat["cuenta_id"], "F-CHOCA"),
        headers=_hdr("facturacion"),
    )
    assert r.status_code == 409
    detalle = r.json()["error"]["detalles"]["ordenes"]
    assert detalle == [{"folio_orden": "OC-OCUPADA", "numero_factura": "F-PRIM"}]


def test_alta_deduplica_la_misma_orden_repetida(
    client: TestClient, db: Session, cat: dict[str, uuid.UUID]
) -> None:
    """Mandar dos veces la misma orden no la cobra dos veces ni rompe la PK compuesta."""
    a = _orden(db, cat, "orden_cerrada", "OC-DUP", subtotal=Decimal("10000.00"))
    db.commit()

    r = client.post(
        "/api/v1/facturacion/clientes",
        json=_payload_factura([a, a], cat["cuenta_id"], "F-DEDUP"),
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
        json=_payload_factura([a, b], cat["cuenta_id"], "F-HAND"),
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
        json=_payload_factura([a, b], cat["cuenta_id"], "F-PAC"),
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
        json=_payload_factura([a, b], cat["cuenta_id"], "F-PAC2"),
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
        json=_payload_factura(a, cat["cuenta_id"], "F-COMBO"),
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
    for numero in ("F-CANC1", "F-CANC2"):
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
            json=_payload_factura(orden, cat["cuenta_id"], "F-VIGENTE"),
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
        json=_payload_factura(a, cat["cuenta_id"], "F-N1"),
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
        json=_payload_factura(orden, cat["cuenta_id"], "F-SEVA"),
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
