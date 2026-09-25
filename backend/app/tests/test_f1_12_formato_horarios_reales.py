"""Pruebas F1-12 · "Formato de Horarios Reales" (ADR-123): junto a "Evidencias de lo
Transmitido" en "Capturar Reales" — misma lista PLANA (sin `orden`/default), pero acepta
CUALQUIER formato (PDF, Excel, TXT, audio...) salvo ejecutables/scripts, validado con
lista NEGRA + firma de ejecutable de Windows ("MZ") sin importar la extensión declarada.

Mismo patrón que `test_f1_10_evidencias_transmitido.py`.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import NotFoundError, register_error_handlers
from app.core.security import Area, CurrentUser
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.incidencia import Incidencia  # noqa: F401 — registra la tabla
from app.modules.ordenes.orden_cliente import (
    OrdenCliente,
    OrdenClienteCreate,
    OrdenClienteRepository,
    OrdenClienteService,
)
from app.modules.ordenes.orden_estacion import (
    OrdenEstacion,
    OrdenEstacionCreate,
    OrdenEstacionDiaCreate,
    OrdenEstacionRepository,
    OrdenEstacionService,
)
from app.modules.ordenes.router import router as ordenes_router
from app.modules.usuarios.models import Usuario

VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")

PDF_BYTES = b"%PDF-1.7 contenido de prueba"
XLSX_BYTES = b"PK\x03\x04 contenido de prueba de excel"
TXT_BYTES = b"contenido de texto plano, sin firma particular"
EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"  # firma PE real


class _ArchivoFalso:
    def __init__(self, filename: str, contenido: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(contenido)


# ══════════════════════════════════════════════════════════════════════════════════
# Fixtures (mismo patrón que test_f1_10_evidencias_transmitido.py)
# ══════════════════════════════════════════════════════════════════════════════════
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
def cat(db: Session) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    uid = uuid.uuid4()
    db.add(
        Usuario(usuario_id=uid, nombre_usuario="dev.admin", email="dev.admin@x.com", area="admin")
    )
    ids["usuario:dev.admin"] = uid

    plaza_id = uuid.uuid4()
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="León"))
    ids["plaza"] = plaza_id

    afiliado_id = uuid.uuid4()
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="OIR Bajío",
            razon_social_afiliado="OIR Bajío SA de CV",
            rfc_afiliado="AUN900101AB1",
        )
    )
    ids["afiliado"] = afiliado_id

    estacion_id = uuid.uuid4()
    db.add(
        Estacion(
            estacion_id=estacion_id,
            afiliado_id=afiliado_id,
            plaza_id=plaza_id,
            nombre_estacion="XHLE-FM",
            frecuencia="97.7 FM",
            tipo_senal="fm",
        )
    )
    ids["estacion"] = estacion_id

    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id,
            nombre_empresa="Radio Publicidad XHMéxico, S.A. de C.V.",
            rfc_empresa="OTE900101AB1",
            direccion_empresa="Av. Constituyentes 1154, Col. Lomas Altas, México, D.F., C.P. 11950",
        )
    )
    ids["empresa"] = empresa_id

    vendedor_id = uuid.uuid4()
    db.add(
        Vendedor(
            vendedor_id=vendedor_id,
            nombre_vendedor="Vendedor Uno",
            porcentaje_comision_default=Decimal("4.00"),
        )
    )
    ids["vendedor"] = vendedor_id

    agencia_id = uuid.uuid4()
    db.add(
        Agencia(
            agencia_id=agencia_id,
            nombre_agencia="OMD México",
            rfc_agencia="AGU900101AB1",
            porcentaje_comision_agencia_default=Decimal("15.00"),
        )
    )
    ids["agencia"] = agencia_id

    anunciante_id = uuid.uuid4()
    db.add(
        Anunciante(
            anunciante_id=anunciante_id,
            agencia_id=agencia_id,
            nombre_comercial="Grupo Bimbo",
            nombre_fiscal="Grupo Bimbo SA de CV",
            rfc_anunciante="ANU900101AB1",
            dias_credito_default=30,
        )
    )
    ids["anunciante"] = anunciante_id

    contrato_id = uuid.uuid4()
    db.add(
        Contrato(
            contrato_id=contrato_id,
            anunciante_id=anunciante_id,
            numero_contrato="CT-001",
            nombre_contrato="Contrato Uno",
            fecha_inicio_contrato=date(2025, 1, 1),
            fecha_fin_contrato=date(2025, 12, 31),
            estado_contrato="vigente",
        )
    )
    ids["contrato"] = contrato_id

    marca_id = uuid.uuid4()
    db.add(Marca(marca_id=marca_id, anunciante_id=anunciante_id, nombre_marca="Marca Uno"))
    ids["marca"] = marca_id

    categoria_id = uuid.uuid4()
    db.add(Categoria(categoria_id=categoria_id, nombre_categoria="Alimentos y bebidas"))
    ids["categoria"] = categoria_id

    db.commit()
    return ids


@pytest.fixture
def oc_svc(db: Session) -> OrdenClienteService:
    repo = OrdenClienteRepository(db, OrdenCliente, search_columns=[OrdenCliente.folio_orden])
    return OrdenClienteService(repo)


@pytest.fixture
def oe_svc(db: Session) -> OrdenEstacionService:
    repo = OrdenEstacionRepository(
        db, OrdenEstacion, search_columns=[OrdenEstacion.folio_orden_estacion]
    )
    return OrdenEstacionService(repo)


def _oc_payload(cat: dict[str, uuid.UUID], **overrides: object) -> OrdenClienteCreate:
    base: dict[str, object] = dict(
        numero_orden_cliente="PO-BIMBO-0419",
        fecha_venta=date(2026, 1, 10),
        empresa_facturadora_id=cat["empresa"],
        vendedor_principal_id=cat["vendedor"],
        anunciante_id=cat["anunciante"],
        agencia_id=cat["agencia"],
        contrato_id=cat["contrato"],
        marca_id=cat["marca"],
        categoria_id=cat["categoria"],
        producto="Pan Bimbo Integral 680g",
        fecha_inicio_campania=date.today() + timedelta(days=30),
        fecha_fin_campania=date.today() + timedelta(days=57),
        duracion_spot="30s",
        precio_unitario=Decimal("1000.00"),
        total_spots=100,
    )
    base.update(overrides)
    return OrdenClienteCreate(**base)


def _oe_payload(
    cat: dict[str, uuid.UUID], orden_id: uuid.UUID, **overrides: object
) -> OrdenEstacionCreate:
    base: dict[str, object] = dict(
        orden_id=orden_id,
        estacion_id=cat["estacion"],
        producto_tarifa="spot",
        duracion_spot="30s",
        precio_spot=Decimal("800.00"),
        observaciones_estacion=None,
        dias=[
            OrdenEstacionDiaCreate(
                fecha_transmision=date.today() + timedelta(days=32),
                hora_inicio=time(7, 0),
                hora_fin=time(9, 0),
                spots_asignados=10,
            ),
        ],
    )
    base.update(overrides)
    return OrdenEstacionCreate(**base)


# ══════════════════════════════════════════════════════════════════════════════════
# Servicio: lista plana + acepta cualquier formato salvo ejecutables
# ══════════════════════════════════════════════════════════════════════════════════
def test_agrega_pdf_excel_y_txt_sin_problema(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    oe_svc.agregar_formato_real(
        oe.orden_estacion_id, _ArchivoFalso("reporte.pdf", PDF_BYTES), VENTAS, almacenamiento
    )
    oe_svc.agregar_formato_real(
        oe.orden_estacion_id, _ArchivoFalso("horarios.xlsx", XLSX_BYTES), VENTAS, almacenamiento
    )
    oe_svc.agregar_formato_real(
        oe.orden_estacion_id, _ArchivoFalso("notas.txt", TXT_BYTES), VENTAS, almacenamiento
    )

    formatos = oe_svc.formatos_reales(oe.orden_estacion_id)
    assert [f.nombre_archivo for f in formatos] == ["reporte.pdf", "horarios.xlsx", "notas.txt"]


def test_rechaza_exe_por_extension(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    from app.integrations.almacenamiento.documentos import ArchivoNoPermitidoError

    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    with pytest.raises(ArchivoNoPermitidoError):
        oe_svc.agregar_formato_real(
            oe.orden_estacion_id, _ArchivoFalso("virus.exe", EXE_BYTES), VENTAS, almacenamiento
        )


def test_rechaza_exe_renombrado_a_pdf_por_firma_mz(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    """El contenido es un ejecutable real (firma MZ) aunque la extensión declarada sea
    .pdf — se rechaza igual, por contenido, no solo por extensión."""
    from app.integrations.almacenamiento.documentos import ArchivoNoPermitidoError

    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    with pytest.raises(ArchivoNoPermitidoError):
        oe_svc.agregar_formato_real(
            oe.orden_estacion_id,
            _ArchivoFalso("disfrazado.pdf", EXE_BYTES),
            VENTAS,
            almacenamiento,
        )


def test_eliminar_formato_real_no_afecta_a_los_demas(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    f0 = oe_svc.agregar_formato_real(
        oe.orden_estacion_id, _ArchivoFalso("reporte.pdf", PDF_BYTES), VENTAS, almacenamiento
    )
    f1 = oe_svc.agregar_formato_real(
        oe.orden_estacion_id, _ArchivoFalso("horarios.xlsx", XLSX_BYTES), VENTAS, almacenamiento
    )

    oe_svc.eliminar_formato_real(oe.orden_estacion_id, f0.orden_estacion_formato_real_id, VENTAS)

    restantes = oe_svc.formatos_reales(oe.orden_estacion_id)
    assert len(restantes) == 1
    assert restantes[0].orden_estacion_formato_real_id == f1.orden_estacion_formato_real_id


def test_obtener_formato_real_de_otra_oe_404(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe1 = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe2 = oe_svc.create(
        _oe_payload(
            cat,
            oc.orden_id,
            dias=[
                OrdenEstacionDiaCreate(
                    fecha_transmision=date.today() + timedelta(days=33),
                    hora_inicio=time(7, 0),
                    hora_fin=time(9, 0),
                    spots_asignados=10,
                )
            ],
        ),
        VENTAS,
    )
    formato_de_oe1 = oe_svc.agregar_formato_real(
        oe1.orden_estacion_id, _ArchivoFalso("reporte.pdf", PDF_BYTES), VENTAS, almacenamiento
    )

    with pytest.raises(NotFoundError):
        oe_svc.obtener_formato_real(
            oe2.orden_estacion_id, formato_de_oe1.orden_estacion_formato_real_id
        )


# ══════════════════════════════════════════════════════════════════════════════════
# HTTP: subir / listar / descargar / borrar + RBAC
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session, tmp_path) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(ordenes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(tmp_path)
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "dev.admin", "X-Dev-Area": area}


def _crear_oc_oe_http(client: TestClient, cat: dict[str, uuid.UUID]) -> str:
    r = client.post(
        "/api/v1/ordenes/clientes",
        json={
            "numero_orden_cliente": "PO-HTTP-FORMATO",
            "fecha_venta": str(date.today()),
            "empresa_facturadora_id": str(cat["empresa"]),
            "vendedor_principal_id": str(cat["vendedor"]),
            "anunciante_id": str(cat["anunciante"]),
            "fecha_inicio_campania": str(date.today() + timedelta(days=1)),
            "fecha_fin_campania": str(date.today() + timedelta(days=30)),
            "duracion_spot": "30s",
            "precio_unitario": "1000.00",
            "total_spots": 10,
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    orden_id = r.json()["orden_id"]

    r = client.post(
        "/api/v1/ordenes/estaciones",
        json={
            "orden_id": orden_id,
            "estacion_id": str(cat["estacion"]),
            "producto_tarifa": "spot",
            "duracion_spot": "30s",
            "precio_spot": "800.00",
            "dias": [
                {
                    "fecha_transmision": str(date.today() + timedelta(days=2)),
                    "hora_inicio": "07:00:00",
                    "hora_fin": "09:00:00",
                    "spots_asignados": 5,
                }
            ],
        },
        headers=_hdr("ventas"),
    )
    assert r.status_code == 201, r.text
    return r.json()["orden_estacion_id"]


def test_http_subir_listar_descargar_borrar_formato_real(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    oe_id = _crear_oc_oe_http(client, cat)

    files = {"archivo": ("horarios.xlsx", XLSX_BYTES, "application/octet-stream")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 201, r.text
    formato = r.json()
    assert formato["nombre_archivo"] == "horarios.xlsx"

    r = client.get(f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales", headers=_hdr("ventas"))
    assert r.status_code == 200
    assert len(r.json()) == 1

    formato_id = formato["orden_estacion_formato_real_id"]
    r = client.get(
        f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales/{formato_id}/archivo",
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200
    assert r.content == XLSX_BYTES
    assert r.headers["content-disposition"] == 'attachment; filename="horarios.xlsx"'

    r = client.delete(
        f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales/{formato_id}", headers=_hdr("ventas")
    )
    assert r.status_code == 204

    r = client.get(f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales", headers=_hdr("ventas"))
    assert r.json() == []


def test_http_rbac_nominas_no_puede_subir_formato_real(
    client: TestClient, cat: dict[str, uuid.UUID]
) -> None:
    oe_id = _crear_oc_oe_http(client, cat)
    files = {"archivo": ("reporte.pdf", PDF_BYTES, "application/pdf")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales",
        files=files,
        headers=_hdr("nominas"),
    )
    assert r.status_code == 403


def test_http_subir_exe_400(client: TestClient, cat: dict[str, uuid.UUID]) -> None:
    oe_id = _crear_oc_oe_http(client, cat)
    files = {"archivo": ("virus.exe", EXE_BYTES, "application/octet-stream")}
    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe_id}/formatos-reales", files=files, headers=_hdr("ventas")
    )
    assert r.status_code == 400
    assert r.json()["error"]["codigo"] == "archivo_no_permitido"
