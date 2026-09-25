"""Pruebas F1-06 · PDFs de OrdenEstacion ("orden de servicio" / "horarios programados" /
"horarios reales"), generados al vuelo desde `orden_estacion_pdf.py` (SQLite, mismo patrón
de fixtures locales que `test_f1_05_ordenes_escritura.py`: no hay spec para este formato,
así que solo se verifica que cada PDF se genera con los datos correctos y que las 2
transiciones (2.2/2.3) están gateadas por el estatus real de la OE."""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.errors import DomainError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.afiliado import Afiliado
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.vendedor import Vendedor
from app.modules.ordenes.incidencia import (
    Incidencia,  # noqa: F401 — registra la tabla en Base.metadata
)
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
    OrdenEstacionDia,
    OrdenEstacionDiaAudioIn,
    OrdenEstacionDiaCreate,
    OrdenEstacionDiaProgramadoIn,
    OrdenEstacionDiaRealIn,
    OrdenEstacionProgramadosIn,
    OrdenEstacionRealesIn,
    OrdenEstacionRepository,
    OrdenEstacionService,
)
from app.modules.ordenes.orden_estacion_pdf import (
    _nombre_material,
    generar_pdf_programados,
    generar_pdf_reales,
    generar_pdf_servicio,
)
from app.modules.usuarios.models import Usuario

VENTAS = CurrentUser(username="dev.admin", area=Area.VENTAS, ip="127.0.0.1")


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
        observaciones_estacion="2 spots no transmitidos por corte",
        dias=[
            OrdenEstacionDiaCreate(
                fecha_transmision=date.today() + timedelta(days=32),
                hora_inicio=time(8, 0),
                hora_fin=time(10, 0),
                spots_asignados=6,
            ),
            OrdenEstacionDiaCreate(
                fecha_transmision=date.today() + timedelta(days=33),
                hora_inicio=time(8, 0),
                hora_fin=time(10, 0),
                spots_asignados=6,
            ),
        ],
    )
    base.update(overrides)
    return OrdenEstacionCreate(**base)


@pytest.fixture
def oe_asignada(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
):
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    return oc, oe


# ── PDF 1: Orden de servicio — siempre disponible ────────────────────────────────
def test_pdf_servicio_se_genera_desde_asignada(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    pdf = generar_pdf_servicio(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


# ── PDF 2: Horarios programados — ADR-121: ya no gateado, disponible desde 'asignada'
def test_pdf_programados_se_genera_desde_asignada(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    pdf = generar_pdf_programados(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_pdf_programados_se_genera_tras_avanzar(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    oe_svc.avanzar_programados(
        oe.orden_estacion_id,
        OrdenEstacionProgramadosIn(
            dias=[
                OrdenEstacionDiaProgramadoIn(
                    fecha_transmision=date.today() + timedelta(days=32), spots_programados=5
                )
            ],
            reporte_programados_ref="ordenes/prog/x_reporte.pdf",
        ),
        VENTAS,
    )
    pdf = generar_pdf_programados(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_pdf_programados_se_genera_con_audios_y_override_por_dia(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada, tmp_path
) -> None:
    """ADR-118: la tabla del PDF #2 ahora depende de `ctx.audios` (antes no se cargaban)
    — con overrides por día, no debe truene generar el PDF."""
    from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal

    class _ArchivoFalso:
        def __init__(self, filename: str, contenido: bytes) -> None:
            self.filename = filename
            self.file = io.BytesIO(contenido)

    _, oe = oe_asignada
    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = b"ID3" + b"\x00" * 40
    uno = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("uno.mp3", contenido), VENTAS, almacenamiento
    )
    dos = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("dos.mp3", contenido), VENTAS, almacenamiento
    )
    dia = oe_svc.dias(oe.orden_estacion_id)[0]
    oe_svc.asignar_audio_dia(
        oe.orden_estacion_id,
        dia.orden_estacion_dia_id,
        OrdenEstacionDiaAudioIn(orden_estacion_audio_id=dos.orden_estacion_audio_id),
        VENTAS,
    )
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)

    pdf = generar_pdf_programados(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")
    assert uno.orden_estacion_audio_id != dos.orden_estacion_audio_id  # sanity: no es el mismo


# ── ADR-118: "Material a Transmitir" en la tabla del PDF de programados ──────────
def test_nombre_material_sin_audios_devuelve_guion() -> None:
    dia = OrdenEstacionDia(orden_estacion_audio_id=None)
    assert _nombre_material(dia, []) == "—"


def test_nombre_material_sin_override_usa_el_primero_subido() -> None:
    uno = OrdenEstacionAudio(
        orden_estacion_audio_id=uuid.uuid4(), nombre_archivo="uno.mp3", orden=0
    )
    dos = OrdenEstacionAudio(
        orden_estacion_audio_id=uuid.uuid4(), nombre_archivo="dos.mp3", orden=1
    )
    dia = OrdenEstacionDia(orden_estacion_audio_id=None)
    assert _nombre_material(dia, [uno, dos]) == "uno.mp3"


def test_nombre_material_con_override_usa_el_del_dia() -> None:
    uno = OrdenEstacionAudio(
        orden_estacion_audio_id=uuid.uuid4(), nombre_archivo="uno.mp3", orden=0
    )
    dos = OrdenEstacionAudio(
        orden_estacion_audio_id=uuid.uuid4(), nombre_archivo="dos.mp3", orden=1
    )
    dia = OrdenEstacionDia(orden_estacion_audio_id=dos.orden_estacion_audio_id)
    assert _nombre_material(dia, [uno, dos]) == "dos.mp3"


# ── PDF 3: Horarios reales — gateado a partir de 2.3 ─────────────────────────────
def test_pdf_reales_rechaza_si_aun_no_se_captura(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    with pytest.raises(DomainError):
        generar_pdf_reales(db, oe.orden_estacion_id)


def test_pdf_reales_se_genera_tras_cerrar(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    fecha_transmision=date.today() + timedelta(days=32), spots_verificados=4
                )
            ],
            reporte_reales_ref="ordenes/reales/x_reporte.pdf",
        ),
        VENTAS,
    )
    pdf = generar_pdf_reales(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_pdf_reales_no_truena_con_descripcion_larga(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """ADR-057: DESCRIPCION/EMISORA van en `Paragraph` (no `str` plano) justo para que un
    texto largo haga word-wrap dentro de su columna en vez de encimarse con la siguiente.
    No hay forma sencilla de aserto visual aquí (verificado manualmente, ver ADR-057); esto
    al menos cubre que reportlab no truena al recibir texto que excede la columna."""
    oc = oc_svc.create(
        _oc_payload(cat, producto="ZAPATOS DE ALTA CALIDAD HECHOS A MANO EN LEÓN GUANAJUATO"),
        VENTAS,
    )
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id), VENTAS)
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[
                OrdenEstacionDiaRealIn(
                    fecha_transmision=date.today() + timedelta(days=32), spots_verificados=4
                )
            ],
        ),
        VENTAS,
    )
    pdf = generar_pdf_reales(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")
