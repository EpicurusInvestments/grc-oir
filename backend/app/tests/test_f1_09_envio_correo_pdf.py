"""Pruebas F1-09 · Envío por correo de los PDFs de OrdenEstacion (ADR-105).

Cubre: envío exitoso (registra la bitácora `LogEnvioCorreoOrdenEstacion` con
`exitoso=True`), envío que falla en el adaptador de correo (se relanza `CorreoError` pero
la bitácora SÍ queda con `exitoso=False` y el detalle del error), el PDF gateado por
sub-estado (p.ej. "reales" antes de 2.3) sigue rechazando ANTES de intentar el envío —
no genera bitácora, historial ordenado del más reciente al más antiguo, 404 de OE
inexistente, y el flujo HTTP completo (endpoint de envío + historial) con el backend
`local` de correo inyectado por dependencia (mismo patrón que `AlmacenamientoLocal` en
`test_f1_07_material_a_transmitir.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import DomainError, NotFoundError, register_error_handlers
from app.core.security import Area, CurrentUser
from app.integrations.correo import get_correo
from app.integrations.correo.errors import CorreoError
from app.integrations.correo.port import Adjunto
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.envio_correo_pdf import (
    EnvioCorreoIn,
    LogEnvioCorreoOrdenEstacion,
    TipoPdfOrdenEstacion,
    enviar_pdf_orden_estacion_por_correo,
    listar_envios_correo,
)
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


class FakeCorreoExitoso:
    def __init__(self) -> None:
        self.enviados: list[dict[str, object]] = []

    def enviar(
        self,
        *,
        destinatario: str,
        asunto: str,
        cuerpo_texto: str,
        adjuntos: list[Adjunto] | None = None,
    ) -> None:
        self.enviados.append({"destinatario": destinatario, "asunto": asunto, "adjuntos": adjuntos})


class FakeCorreoFalla:
    def enviar(
        self,
        *,
        destinatario: str,
        asunto: str,
        cuerpo_texto: str,
        adjuntos: list[Adjunto] | None = None,
    ) -> None:
        raise CorreoError("SES rechazó el envío (remitente no verificado).")


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
    db.add(Plaza(plaza_id=plaza_id, nombre_plaza="CDMX"))
    ids["plaza"] = plaza_id

    afiliado_id = uuid.uuid4()
    db.add(
        Afiliado(
            afiliado_id=afiliado_id,
            nombre_afiliado="Afiliado Uno",
            razon_social_afiliado="Afiliado Uno SA de CV",
            rfc_afiliado="AUN900101AB1",
            contacto_email="contacto@afiliado-uno.com",
        )
    )
    ids["afiliado"] = afiliado_id

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
    ids["estacion"] = estacion_id

    empresa_id = uuid.uuid4()
    db.add(
        EmpresaFacturadora(
            empresa_facturadora_id=empresa_id, nombre_empresa="OIR Test", rfc_empresa="OTE900101AB1"
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
            nombre_agencia="Agencia Uno",
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
            nombre_comercial="Anunciante Uno",
            nombre_fiscal="Anunciante Uno SA de CV",
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
    db.add(Categoria(categoria_id=categoria_id, nombre_categoria="Categoria Uno"))
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
        numero_orden_cliente="NUM-001",
        fecha_venta=date(2026, 1, 10),
        empresa_facturadora_id=cat["empresa"],
        vendedor_principal_id=cat["vendedor"],
        anunciante_id=cat["anunciante"],
        agencia_id=cat["agencia"],
        contrato_id=cat["contrato"],
        marca_id=cat["marca"],
        categoria_id=cat["categoria"],
        producto="Producto de prueba",
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


@pytest.fixture
def oe_asignada(db: Session, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat):
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    return oc, oe


# ══════════════════════════════════════════════════════════════════════════════════
# Servicio: enviar_pdf_orden_estacion_por_correo
# ══════════════════════════════════════════════════════════════════════════════════
def test_enviar_pdf_servicio_exitoso_registra_bitacora(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    correo = FakeCorreoExitoso()

    log = enviar_pdf_orden_estacion_por_correo(
        db,
        oe.orden_estacion_id,
        TipoPdfOrdenEstacion.SERVICIO,
        EnvioCorreoIn(destinatario_email="contacto@afiliado-uno.com"),
        VENTAS,
        correo,
    )

    assert log.exitoso is True
    assert log.mensaje_error is None
    assert log.destinatario_email == "contacto@afiliado-uno.com"
    assert log.tipo_pdf == TipoPdfOrdenEstacion.SERVICIO
    assert log.usuario == "dev.admin"
    assert len(correo.enviados) == 1
    assert correo.enviados[0]["destinatario"] == "contacto@afiliado-uno.com"

    guardado = db.get(LogEnvioCorreoOrdenEstacion, log.log_envio_correo_id)
    assert guardado is not None
    assert guardado.exitoso is True


def test_enviar_pdf_falla_registra_bitacora_y_relanza_502(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    correo = FakeCorreoFalla()

    with pytest.raises(CorreoError):
        enviar_pdf_orden_estacion_por_correo(
            db,
            oe.orden_estacion_id,
            TipoPdfOrdenEstacion.SERVICIO,
            EnvioCorreoIn(destinatario_email="contacto@afiliado-uno.com"),
            VENTAS,
            correo,
        )

    registros = db.scalars(select(LogEnvioCorreoOrdenEstacion)).all()
    assert len(registros) == 1
    assert registros[0].exitoso is False
    assert "SES rechazó" in (registros[0].mensaje_error or "")


def test_enviar_pdf_reales_antes_de_hora_400_sin_bitacora(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    correo = FakeCorreoExitoso()

    with pytest.raises(DomainError):
        enviar_pdf_orden_estacion_por_correo(
            db,
            oe.orden_estacion_id,
            TipoPdfOrdenEstacion.REALES,
            EnvioCorreoIn(destinatario_email="contacto@afiliado-uno.com"),
            VENTAS,
            correo,
        )

    assert correo.enviados == []
    assert db.scalars(select(LogEnvioCorreoOrdenEstacion)).all() == []


def test_enviar_pdf_oe_inexistente_404(db: Session) -> None:
    with pytest.raises(NotFoundError):
        enviar_pdf_orden_estacion_por_correo(
            db,
            uuid.uuid4(),
            TipoPdfOrdenEstacion.SERVICIO,
            EnvioCorreoIn(destinatario_email="alguien@x.com"),
            VENTAS,
            FakeCorreoExitoso(),
        )


def test_listar_envios_correo_mas_reciente_primero(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    correo = FakeCorreoExitoso()

    enviar_pdf_orden_estacion_por_correo(
        db,
        oe.orden_estacion_id,
        TipoPdfOrdenEstacion.SERVICIO,
        EnvioCorreoIn(destinatario_email="primero@x.com"),
        VENTAS,
        correo,
    )
    enviar_pdf_orden_estacion_por_correo(
        db,
        oe.orden_estacion_id,
        TipoPdfOrdenEstacion.SERVICIO,
        EnvioCorreoIn(destinatario_email="segundo@x.com"),
        VENTAS,
        correo,
    )

    historial = listar_envios_correo(db, oe.orden_estacion_id)
    assert len(historial) == 2
    assert historial[0].destinatario_email == "segundo@x.com"
    assert historial[1].destinatario_email == "primero@x.com"


# ══════════════════════════════════════════════════════════════════════════════════
# HTTP: endpoint de envío + historial
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(ordenes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_correo] = lambda: FakeCorreoExitoso()
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "dev.admin", "X-Dev-Area": area}


def test_http_enviar_pdf_correo_y_listar_historial(
    client: TestClient, db: Session, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/pdf/servicio/enviar-correo",
        json={"destinatario_email": "contacto@afiliado-uno.com"},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exitoso"] is True
    assert body["destinatario_email"] == "contacto@afiliado-uno.com"
    assert body["tipo_pdf"] == "servicio"

    r2 = client.get(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/envios-correo", headers=_hdr("ventas")
    )
    assert r2.status_code == 200, r2.text
    historial = r2.json()
    assert len(historial) == 1
    assert historial[0]["destinatario_email"] == "contacto@afiliado-uno.com"


def test_http_enviar_pdf_correo_email_invalido_422(
    client: TestClient, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)

    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/pdf/servicio/enviar-correo",
        json={"destinatario_email": "no-es-un-correo"},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 422
