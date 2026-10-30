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
        producto_tarifa="spot",
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


def test_pdf_servicio_no_truena_con_muchos_dias(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    """ADR-131 (corrige un bug real): con ADR-127 (varios spots por fecha) una OE puede
    tener MUCHAS más filas de `OrdenEstacionDia` que antes (un spot = una fila, no un
    día = una fila). `tabla_dias` anidada dentro de la celda del "marco" (borde) no podía
    partirse entre páginas — reportlab tronaba con `LayoutError` en cuanto la tabla de
    días no cabía completa en lo que quedaba de una página."""
    oc = oc_svc.create(_oc_payload(cat, total_spots=200), VENTAS)
    fecha_base = date.today() + timedelta(days=32)
    dias = [
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha_base + timedelta(days=i // 20),
            hora_inicio=time(7, i % 20),
            hora_fin=time(7, i % 20),
            spots_asignados=1,
        )
        for i in range(80)
    ]
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id, dias=dias), VENTAS)

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
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(
        oe.orden_estacion_id,
        OrdenEstacionProgramadosIn(
            dias=[OrdenEstacionDiaProgramadoIn(orden_estacion_dia_id=dia_id, spots_programados=5)],
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
# ADR-196 (corrige un bug real): `_nombre_material` ya NO tiene un "default compartido"
# (ADR-187 lo eliminó: 1 material por spot, asignado explícitamente por posición al
# generar/editar) — sin `orden_estacion_audio_id` propio, regresa `None` (nada que
# mostrar para ESE spot en particular), no un fallback a `audios[0]`.
def test_nombre_material_sin_audios_devuelve_none() -> None:
    dia = OrdenEstacionDia(orden_estacion_audio_id=None)
    assert _nombre_material(dia, []) is None


def test_nombre_material_sin_override_propio_devuelve_none() -> None:
    uno = OrdenEstacionAudio(
        orden_estacion_audio_id=uuid.uuid4(), nombre_archivo="uno.mp3", orden=0
    )
    dos = OrdenEstacionAudio(
        orden_estacion_audio_id=uuid.uuid4(), nombre_archivo="dos.mp3", orden=1
    )
    dia = OrdenEstacionDia(orden_estacion_audio_id=None)
    assert _nombre_material(dia, [uno, dos]) is None


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
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[OrdenEstacionDiaRealIn(orden_estacion_dia_id=dia_id, spots_verificados=4)],
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
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[OrdenEstacionDiaRealIn(orden_estacion_dia_id=dia_id, spots_verificados=4)],
        ),
        VENTAS,
    )
    pdf = generar_pdf_reales(db, oe.orden_estacion_id)
    assert pdf.startswith(b"%PDF")


# ── ADR-192 (corrige un bug real): los 3 PDFs habían sido consolidados (ADR-118/155/156)
# a un solo horario, asumiendo que `hora_inicio == hora_fin` siempre (ADR-108) — supuesto
# inválido desde ADR-184 en adelante (la captura web volvió a un rango real). Vuelven a
# mostrar AMBOS — se extrae el texto real del PDF (no solo "no truena") para probarlo. ──
def _texto_pdf(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_pdf_servicio_muestra_hora_inicio_y_hora_fin(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    texto = _texto_pdf(generar_pdf_servicio(db, oe.orden_estacion_id))
    assert "Hora Inicio" in texto
    assert "Hora Fin" in texto
    assert "08:00:00" in texto
    assert "10:00:00" in texto


def test_pdf_programados_muestra_rango_de_horario(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    # El salto de línea dentro de la columna angosta puede partir "10:00 am" entre 2
    # renglones al extraer texto (word-wrap de reportlab) — se normalizan espacios en
    # blanco/saltos de línea a un solo espacio antes de comparar.
    texto = " ".join(_texto_pdf(generar_pdf_programados(db, oe.orden_estacion_id)).lower().split())
    assert "8:00 am a 10:00 am" in texto


# ADR-196 (corrige un bug real de ADR-192, petición del usuario): "HORA" en el PDF de
# Reales vuelve a mostrar UN SOLO horario (el punto real de ese spot, `hora_inicio`) —
# NO el rango `inicio - fin` que ADR-192 había restaurado por error (desde ADR-186,
# `hora_fin` es el fin de rango COMPARTIDO entre todos los spots del día, no algo propio
# de un renglón individual — mostrarlo como rango ahí confundía más de lo que aclaraba).
def test_pdf_reales_muestra_un_solo_horario_no_un_rango(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[OrdenEstacionDiaRealIn(orden_estacion_dia_id=dia_id, spots_verificados=4)],
        ),
        VENTAS,
    )
    texto = _texto_pdf(generar_pdf_reales(db, oe.orden_estacion_id))
    assert "08:00" in texto
    assert "08:00 - 10:00" not in texto


# ── ADR-193 (petición del usuario): "Marca" y "Producto" (`oe.producto_tarifa`, catálogo
# F0-06) no aparecían en NINGÚN PDF — "Producto"/"Campaña" eran, de hecho, el MISMO campo
# (`oc.producto`, texto libre) mal etiquetado como "Producto". Ahora son 3 campos
# distintos en los 3 PDFs: Marca (`ctx.marca.nombre_marca`), Campaña (`oc.producto`,
# "Pan Bimbo Integral 680g" en el fixture) y Producto (`oe.producto_tarifa`, "spot"). ──
def test_pdf_servicio_muestra_marca_y_producto_del_catalogo(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    texto = _texto_pdf(generar_pdf_servicio(db, oe.orden_estacion_id))
    assert "Marca Uno" in texto
    assert "Campaña" in texto  # "Producto" (oc.producto) se relabeled a "Campaña"
    # "Producto" (oe.producto_tarifa) y "Campaña" (oc.producto) comparten el mismo
    # valor de prueba ("spot" NO es el caso — ver fixture: producto_tarifa="spot",
    # producto="Pan Bimbo Integral 680g" — así que ambos textos deben verse, distintos.
    assert "Pan Bimbo Integral 680g" in texto
    assert "spot" in texto.lower()


def test_pdf_programados_muestra_marca_y_producto_del_catalogo(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada
    texto = _texto_pdf(generar_pdf_programados(db, oe.orden_estacion_id))
    assert "MARCA" in texto
    assert "MARCA UNO" in texto.upper()
    assert "PRODUCTO" in texto
    assert "SPOT" in texto.upper()


def test_pdf_reales_muestra_marca_y_producto_del_catalogo(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[OrdenEstacionDiaRealIn(orden_estacion_dia_id=dia_id, spots_verificados=4)],
        ),
        VENTAS,
    )
    texto = _texto_pdf(generar_pdf_reales(db, oe.orden_estacion_id)).upper()
    assert "MARCA UNO" in texto
    assert "PRODUCTO" in texto


# ── ADR-221c (petición del usuario, con 3 capturas): en Programados faltaba el número de
# spots POR DÍA (antes solo se veía el total agregado "TOTAL SPOTS" del encabezado); en
# Reales sobraba una columna "SPOTS" por renglón (cada renglón YA es un solo spot, ADR-127,
# así que siempre mostraba "1" sin aportar nada); y en ambos la descripción de la emisora
# venía incompleta (solo nombre + frecuencia, sin siglas ni tipo de señal). ──
def test_pdf_programados_muestra_spots_por_dia(db: Session, oe_asignada) -> None:
    _, oe = oe_asignada  # 2 días, 6 spots_asignados cada uno (ver `_oe_payload`).
    texto = " ".join(_texto_pdf(generar_pdf_programados(db, oe.orden_estacion_id)).split())
    assert texto.count("Spots: 6") == 2


def test_pdf_programados_agrupa_spots_por_dia_cuando_hay_varios_renglones_la_misma_fecha(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    fecha = date.today() + timedelta(days=32)
    dias = [
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha, hora_inicio=time(8, 0), hora_fin=time(18, 0), spots_asignados=1
        ),
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha, hora_inicio=time(9, 0), hora_fin=time(18, 0), spots_asignados=1
        ),
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha,
            hora_inicio=time(10, 0),
            hora_fin=time(18, 0),
            spots_asignados=1,
        ),
    ]
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id, dias=dias), VENTAS)
    texto = " ".join(_texto_pdf(generar_pdf_programados(db, oe.orden_estacion_id)).split())
    assert "Spots: 3" in texto  # 1 renglón para la fecha, suma de los 3 (ADR-196).


def test_pdf_programados_descripcion_de_estacion_incluye_siglas_y_tipo_senal(
    db: Session, oe_asignada
) -> None:
    _, oe = oe_asignada
    texto = _texto_pdf(generar_pdf_programados(db, oe.orden_estacion_id))
    # Fixture `cat["estacion"]`: nombre_estacion="XHLE-FM", frecuencia="97.7 FM",
    # tipo_senal="fm" (sin siglas propias) — el tipo de señal (FM) debe verse junto al
    # nombre, no solo nombre+frecuencia como antes.
    assert "FM XHLE-FM" in texto


def test_pdf_reales_descripcion_de_emisora_incluye_siglas_y_tipo_senal(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[OrdenEstacionDiaRealIn(orden_estacion_dia_id=dia_id, spots_verificados=4)],
        ),
        VENTAS,
    )
    texto = _texto_pdf(generar_pdf_reales(db, oe.orden_estacion_id)).upper()
    assert "FM XHLE-FM" in texto


def test_pdf_reales_ya_no_tiene_columna_spots_por_renglon(
    db: Session, oe_svc: OrdenEstacionService, oe_asignada
) -> None:
    _, oe = oe_asignada
    dia_id = oe_svc.dias(oe.orden_estacion_id)[0].orden_estacion_dia_id
    oe_svc.avanzar_programados(oe.orden_estacion_id, OrdenEstacionProgramadosIn(), VENTAS)
    oe_svc.avanzar_reales(
        oe.orden_estacion_id,
        OrdenEstacionRealesIn(
            dias=[OrdenEstacionDiaRealIn(orden_estacion_dia_id=dia_id, spots_verificados=4)],
        ),
        VENTAS,
    )
    texto = " ".join(_texto_pdf(generar_pdf_reales(db, oe.orden_estacion_id)).split()).upper()
    assert "FECHA HORA DESCRIPCION EMISORA" in texto
    assert "FECHA HORA SPOTS DESCRIPCION" not in texto


# ── ADR-196 (corrige un bug real, petición del usuario): Servicio y Programados vuelven
# a mostrar UN SOLO renglón por FECHA (como la grid de captura, ADR-185) — antes
# mostraban 1 renglón por SPOT (varias filas reales de la misma fecha, ADR-127), con
# horarios distintos repitiendo la misma fecha varias veces. "Capturar reales"/el PDF de
# Reales NO se agrupan, siguen siendo 1 renglón por spot (confirmado aparte, arriba). ──
def test_pdf_servicio_agrupa_varias_filas_reales_de_la_misma_fecha_en_un_solo_renglon(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
) -> None:
    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    fecha = date.today() + timedelta(days=32)
    dias = [
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha, hora_inicio=time(8, 0), hora_fin=time(18, 0), spots_asignados=1
        ),
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha, hora_inicio=time(9, 0), hora_fin=time(18, 0), spots_asignados=1
        ),
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha,
            hora_inicio=time(10, 0),
            hora_fin=time(18, 0),
            spots_asignados=1,
        ),
    ]
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id, dias=dias), VENTAS)

    texto = _texto_pdf(generar_pdf_servicio(db, oe.orden_estacion_id))
    # 1 SOLO renglón para esa fecha: Hora Inicio = la más temprana (08:00:00), Hora Fin =
    # el fin de rango compartido (18:00:00), Spots = la suma (3) — no 3 renglones sueltos
    # con 09:00:00/10:00:00 viéndose cada uno por separado.
    assert texto.count(fecha.strftime("%d/%m/%Y")) == 1
    assert "08:00:00" in texto
    assert "18:00:00" in texto
    assert "09:00:00" not in texto
    assert "10:00:00" not in texto


def test_pdf_programados_agrupa_por_fecha_y_lista_los_materiales_distintos_separados_por_coma(
    db: Session,
    oc_svc: OrdenClienteService,
    oe_svc: OrdenEstacionService,
    cat: dict[str, uuid.UUID],
    tmp_path,
) -> None:
    from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal

    class _ArchivoFalso:
        def __init__(self, filename: str, contenido: bytes) -> None:
            self.filename = filename
            self.file = io.BytesIO(contenido)

    oc = oc_svc.create(_oc_payload(cat), VENTAS)
    fecha = date.today() + timedelta(days=32)
    dias = [
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha, hora_inicio=time(8, 0), hora_fin=time(18, 0), spots_asignados=1
        ),
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha, hora_inicio=time(9, 0), hora_fin=time(18, 0), spots_asignados=1
        ),
        OrdenEstacionDiaCreate(
            fecha_transmision=fecha,
            hora_inicio=time(10, 0),
            hora_fin=time(18, 0),
            spots_asignados=1,
        ),
    ]
    oe = oe_svc.create(_oe_payload(cat, oc.orden_id, dias=dias), VENTAS)

    almacenamiento = AlmacenamientoLocal(tmp_path)
    contenido = b"ID3" + b"\x00" * 40
    uno = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("uno.mp3", contenido), VENTAS, almacenamiento
    )
    dos = oe_svc.agregar_audio(
        oe.orden_estacion_id, _ArchivoFalso("dos.mp3", contenido), VENTAS, almacenamiento
    )
    dias_reales = oe_svc.dias(oe.orden_estacion_id)
    dia_8 = next(d for d in dias_reales if d.hora_inicio == time(8, 0))
    dia_9 = next(d for d in dias_reales if d.hora_inicio == time(9, 0))
    # dia_10 (hora_inicio=10:00) se queda SIN override — no aporta un 3er nombre.
    oe_svc.asignar_audio_dia(
        oe.orden_estacion_id,
        dia_8.orden_estacion_dia_id,
        OrdenEstacionDiaAudioIn(orden_estacion_audio_id=uno.orden_estacion_audio_id),
        VENTAS,
    )
    oe_svc.asignar_audio_dia(
        oe.orden_estacion_id,
        dia_9.orden_estacion_dia_id,
        OrdenEstacionDiaAudioIn(orden_estacion_audio_id=dos.orden_estacion_audio_id),
        VENTAS,
    )

    texto = " ".join(_texto_pdf(generar_pdf_programados(db, oe.orden_estacion_id)).split())
    assert texto.count("Material a Transmitir") == 1  # 1 SOLO renglón para esa fecha
    assert "uno.mp3, dos.mp3" in texto
