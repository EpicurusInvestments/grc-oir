"""Pruebas F1-11 · Envío por correo "bundle" de la Orden de Transmisión (ADR-120).

Cubre: envío exitoso a TODOS los contactos activos con correo del afiliado (ignora
inactivos y los que no tienen correo cargado), adjunta el PDF de Programados + todo el
Material a Transmitir, 400 si el afiliado no tiene ningún contacto activo con correo,
falla del adaptador de correo (bitácora igual queda registrada, `exitoso=False`), 404 de
OE inexistente, y el flujo HTTP completo con el backend `local` de correo/almacenamiento
inyectado por dependencia (mismo patrón que `test_f1_09_envio_correo_pdf.py`).
"""

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
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.correo import get_correo
from app.integrations.correo.errors import CorreoError
from app.integrations.correo.port import Adjunto
from app.modules.catalogos.afiliado import Afiliado, ContactoAfiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.envio_correo_pdf import (
    LogEnvioCorreoOrdenEstacion,
    TipoPdfOrdenEstacion,
    enviar_correo_orden_transmision,
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
    OrdenEstacionAudio,
    OrdenEstacionCreate,
    OrdenEstacionDiaCreate,
    OrdenEstacionProgramadosIn,
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
        destinatario: str | list[str],
        asunto: str,
        cuerpo_texto: str,
        adjuntos: list[Adjunto] | None = None,
    ) -> None:
        self.enviados.append(
            {"destinatario": destinatario, "asunto": asunto, "adjuntos": adjuntos}
        )


class FakeCorreoFalla:
    def enviar(
        self,
        *,
        destinatario: str | list[str],
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
def almacenamiento(tmp_path) -> AlmacenamientoLocal:
    return AlmacenamientoLocal(tmp_path)


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
            contacto_email="legado@afiliado-uno.com",
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
def oe_en_transmision(db: Session, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat):
    """OE avanzada a 2.2 (`en_transmision`) — mínimo requerido por
    `generar_pdf_programados` (rechaza mientras siga en `asignada`)."""
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe = oe_svc.avanzar_programados(
        oe.orden_estacion_id, OrdenEstacionProgramadosIn(dias=[]), VENTAS
    )
    return oc, oe


def _agregar_contacto(
    db: Session, afiliado_id: uuid.UUID, *, nombre: str, email: str | None, activo: bool = True
) -> None:
    db.add(
        ContactoAfiliado(
            contacto_afiliado_id=uuid.uuid4(),
            afiliado_id=afiliado_id,
            nombre_contacto=nombre,
            email_contacto=email,
            activo=activo,
        )
    )
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════════
# Servicio: enviar_correo_orden_transmision
# ══════════════════════════════════════════════════════════════════════════════════
def test_manda_solo_a_contactos_activos_con_correo_e_ignora_los_demas(
    db: Session, oe_en_transmision, almacenamiento
) -> None:
    _, oe = oe_en_transmision
    _agregar_contacto(db, _afiliado_de(db, oe), nombre="Activo Uno", email="uno@x.com")
    correo = FakeCorreoExitoso()

    log = enviar_correo_orden_transmision(db, oe.orden_estacion_id, VENTAS, correo, almacenamiento)

    assert log.exitoso is True
    assert log.tipo_pdf == TipoPdfOrdenEstacion.ORDEN_TRANSMISION
    assert "uno@x.com" in log.destinatario_email
    assert len(correo.enviados) == 1
    assert correo.enviados[0]["asunto"] == "Orden de Transmisión"


def _afiliado_de(db: Session, oe: OrdenEstacion) -> uuid.UUID:
    estacion = db.get(Estacion, oe.estacion_id)
    assert estacion is not None
    return estacion.afiliado_id


def test_ignora_contactos_inactivos_o_sin_correo(
    db: Session, oe_en_transmision, almacenamiento
) -> None:
    _, oe = oe_en_transmision
    afiliado_id = _afiliado_de(db, oe)
    _agregar_contacto(db, afiliado_id, nombre="Activo con correo", email="si@x.com")
    _agregar_contacto(
        db, afiliado_id, nombre="Inactivo", email="no-deberia-salir@x.com", activo=False
    )
    _agregar_contacto(db, afiliado_id, nombre="Sin correo", email=None)
    correo = FakeCorreoExitoso()

    log = enviar_correo_orden_transmision(db, oe.orden_estacion_id, VENTAS, correo, almacenamiento)

    assert log.destinatario_email == "si@x.com"


def test_sin_contactos_activos_con_correo_400(
    db: Session, oe_en_transmision, almacenamiento
) -> None:
    _, oe = oe_en_transmision
    afiliado_id = _afiliado_de(db, oe)
    _agregar_contacto(db, afiliado_id, nombre="Inactivo", email="x@x.com", activo=False)
    correo = FakeCorreoExitoso()

    with pytest.raises(DomainError):
        enviar_correo_orden_transmision(db, oe.orden_estacion_id, VENTAS, correo, almacenamiento)

    assert correo.enviados == []
    assert db.scalars(select(LogEnvioCorreoOrdenEstacion)).all() == []


def test_adjunta_pdf_programados_y_todos_los_audios(
    db: Session, oe_en_transmision, almacenamiento
) -> None:
    _, oe = oe_en_transmision
    afiliado_id = _afiliado_de(db, oe)
    _agregar_contacto(db, afiliado_id, nombre="Activo", email="uno@x.com")

    for i, nombre in enumerate(["material_a.mp3", "material_b.wav"]):
        ref = almacenamiento.subir(
            prefijo=f"orden_estacion/audios/{oe.orden_estacion_id}/",
            nombre_archivo=nombre,
            contenido=b"contenido-falso",
            content_type="audio/mpeg",
        )
        db.add(
            OrdenEstacionAudio(
                orden_estacion_audio_id=uuid.uuid4(),
                orden_estacion_id=oe.orden_estacion_id,
                ref=ref,
                nombre_archivo=nombre,
                orden=i,
            )
        )
    db.commit()

    correo = FakeCorreoExitoso()
    enviar_correo_orden_transmision(db, oe.orden_estacion_id, VENTAS, correo, almacenamiento)

    adjuntos = correo.enviados[0]["adjuntos"]
    nombres_adjuntos = [nombre for nombre, _contenido, _tipo in adjuntos]
    assert "horarios_programados.pdf" in nombres_adjuntos
    assert "material_a.mp3" in nombres_adjuntos
    assert "material_b.wav" in nombres_adjuntos
    assert len(nombres_adjuntos) == 3


def test_falla_registra_bitacora_y_relanza(db: Session, oe_en_transmision, almacenamiento) -> None:
    _, oe = oe_en_transmision
    afiliado_id = _afiliado_de(db, oe)
    _agregar_contacto(db, afiliado_id, nombre="Activo", email="uno@x.com")
    correo = FakeCorreoFalla()

    with pytest.raises(CorreoError):
        enviar_correo_orden_transmision(db, oe.orden_estacion_id, VENTAS, correo, almacenamiento)

    registros = db.scalars(select(LogEnvioCorreoOrdenEstacion)).all()
    assert len(registros) == 1
    assert registros[0].exitoso is False
    assert registros[0].tipo_pdf == "orden_transmision"


def test_oe_inexistente_404(db: Session, almacenamiento) -> None:
    with pytest.raises(NotFoundError):
        enviar_correo_orden_transmision(
            db, uuid.uuid4(), VENTAS, FakeCorreoExitoso(), almacenamiento
        )


# ══════════════════════════════════════════════════════════════════════════════════
# HTTP: endpoint de envío
# ══════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session, almacenamiento: AlmacenamientoLocal) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(ordenes_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_correo] = lambda: FakeCorreoExitoso()
    app.dependency_overrides[get_almacenamiento] = lambda: almacenamiento
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "dev.admin", "X-Dev-Area": area}


def test_http_enviar_correo_orden_transmision(
    client: TestClient,
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat,
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe = oe_svc.avanzar_programados(
        oe.orden_estacion_id, OrdenEstacionProgramadosIn(dias=[]), VENTAS
    )
    _agregar_contacto(db, cat["afiliado"], nombre="Activo", email="uno@x.com")

    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/correo-orden-transmision",
        headers=_hdr("ventas"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exitoso"] is True
    assert body["tipo_pdf"] == "orden_transmision"
    assert body["destinatario_email"] == "uno@x.com"


def test_http_sin_contactos_activos_400(
    client: TestClient, oc_svc: OrdenClienteService, oe_svc: OrdenEstacionService, cat
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe = oe_svc.avanzar_programados(
        oe.orden_estacion_id, OrdenEstacionProgramadosIn(dias=[]), VENTAS
    )

    r = client.post(
        f"/api/v1/ordenes/estaciones/{oe.orden_estacion_id}/correo-orden-transmision",
        headers=_hdr("ventas"),
    )
    assert r.status_code == 400, r.text
