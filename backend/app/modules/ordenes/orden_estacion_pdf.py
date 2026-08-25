"""PDFs de OrdenEstacion — "Orden de servicio" (2.1), "Horarios programados" (2.2) y
"Horarios reales" (2.3), generados AL VUELO a partir del estado actual de la orden (no
se guarda ningún archivo: cada descarga refleja los datos más recientes).

No hay spec para este formato (confirmado: no está en la propuesta ni en la especificación
BD v2) — nace de 3 PDFs de referencia que el equipo compartió, replicados en su estructura
de campos. Generado con **reportlab** (puro Python, sin dependencias de sistema) en vez de
WeasyPrint: WeasyPrint requiere Pango/GObject instalados en el sistema operativo, lo que
rompe el desarrollo local en Windows sin Docker (probado y descartado).

Logos de OIR y Grupo Radio Centro: se leen de `app/assets/logos/` (`oir.*`/`grc.*` —
ver README ahí) — si el archivo no existe, el PDF se genera igual, sin ese logo. El
nombre de la empresa/domicilio que aparece en el encabezado y pie sale de
`EmpresaFacturadora` (catálogo F0), NO de un texto fijo — cambia según qué empresa
facturadora tenga la OrdenCliente de origen.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.errors import DomainError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.ordenes.orden_cliente import OrdenCliente
from app.modules.ordenes.orden_estacion import (
    EstatusOrdenEstacion,
    OrdenEstacion,
    OrdenEstacionDia,
)
from app.modules.ordenes.verificacion import Verificacion

IVA_RATE = Decimal(str(settings.iva_rate))
CENTAVOS = Decimal("0.01")

MESES_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ── Helpers de formato ──────────────────────────────────────────────────────────
def _moneda(valor: Decimal) -> str:
    return f"${valor:,.2f}"


def _fecha_corta(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _fecha_larga(d: date) -> str:
    return f"{d.day} {MESES_ES[d.month - 1].upper()} {d.year}"


def _dia_semana(d: date) -> str:
    return DIAS_ES[d.weekday()]


def _hora_12h(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0").lower()


def _hora_24h(t: time) -> str:
    return t.strftime("%H:%M")


def _nombre_adjunto(ref: str) -> str:
    """Mismo criterio que `nombreDeAdjuntoRef` del frontend: quita el prefijo
    `<uuid_hex>_` de la clave de almacenamiento para mostrar el nombre original."""
    base = ref.rsplit("/", 1)[-1]
    idx = base.find("_")
    return base[idx + 1 :] if idx >= 0 else base


def _letra_sufijo(folio_orden_estacion: str) -> str:
    return folio_orden_estacion[-1] if folio_orden_estacion else ""


def _generado_el() -> str:
    ahora = datetime.now()
    hora = ahora.strftime("%I:%M %p").lstrip("0").lower()
    return f"{ahora.day}/{MESES_ES[ahora.month - 1]}/{ahora.year} {hora}"


# ── Logos (app/assets/logos/ — ver README ahí) ───────────────────────────────────
_LOGOS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "logos"
_LOGO_ALTO = 1.1 * cm


def _ruta_logo(nombre: str) -> Path | None:
    for extension in (".jpg", ".jpeg", ".png"):
        ruta = _LOGOS_DIR / f"{nombre}{extension}"
        if ruta.exists():
            return ruta
    return None


def _logo_flowable(nombre: str):
    """Imagen escalada a `_LOGO_ALTO` conservando proporción, o un espacio en
    blanco del mismo alto si el archivo no existe (el PDF no debe fallar por
    esto — ver README de la carpeta de logos)."""
    ruta = _ruta_logo(nombre)
    if ruta is None:
        return Spacer(1, _LOGO_ALTO)
    ancho_natural, alto_natural = ImageReader(str(ruta)).getSize()
    ancho = _LOGO_ALTO * (ancho_natural / alto_natural)
    return Image(str(ruta), width=ancho, height=_LOGO_ALTO)


def _encabezado(nombre_empresa: str, subtitulo: str, ancho_disponible: float) -> Table:
    ancho_logo_col = 3.5 * cm
    tabla = Table(
        [
            [
                _logo_flowable("oir"),
                [Paragraph(nombre_empresa, _TITULO), Paragraph(subtitulo, _SUBTITULO)],
                _logo_flowable("grc"),
            ]
        ],
        colWidths=[ancho_logo_col, ancho_disponible - 2 * ancho_logo_col, ancho_logo_col],
    )
    tabla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ]
        )
    )
    return tabla


# ── Carga de datos ──────────────────────────────────────────────────────────────
class _Contexto:
    def __init__(
        self,
        oe: OrdenEstacion,
        oc: OrdenCliente,
        estacion: Estacion,
        plaza: Plaza,
        anunciante: Anunciante,
        agencia: Agencia | None,
        empresa: EmpresaFacturadora,
        dias: list[OrdenEstacionDia],
    ) -> None:
        self.oe = oe
        self.oc = oc
        self.estacion = estacion
        self.plaza = plaza
        self.anunciante = anunciante
        self.agencia = agencia
        self.empresa = empresa
        self.dias = dias


def _cargar_contexto(db: Session, orden_estacion_id: uuid.UUID) -> _Contexto:
    oe = db.get(OrdenEstacion, orden_estacion_id)
    if oe is None:
        raise NotFoundError(
            "OrdenEstacion no encontrada.", detalles={"orden_estacion_id": str(orden_estacion_id)}
        )
    oc = db.get(OrdenCliente, oe.orden_id)
    estacion = db.get(Estacion, oe.estacion_id)
    plaza = db.get(Plaza, oe.plaza_id)
    anunciante = db.get(Anunciante, oe.anunciante_id)
    agencia = db.get(Agencia, oe.agencia_id) if oe.agencia_id else None
    empresa = db.get(EmpresaFacturadora, oc.empresa_facturadora_id) if oc else None
    if oc is None or estacion is None or plaza is None or anunciante is None or empresa is None:
        raise NotFoundError("Faltan datos relacionados de la OrdenEstacion para generar el PDF.")
    dias = list(
        db.scalars(
            select(OrdenEstacionDia)
            .where(OrdenEstacionDia.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionDia.fecha_transmision)
        )
    )
    return _Contexto(oe, oc, estacion, plaza, anunciante, agencia, empresa, dias)


def _rango_campania(oc: OrdenCliente) -> str:
    return f"{_fecha_larga(oc.fecha_inicio_campania)} AL {_fecha_larga(oc.fecha_fin_campania)}"


def _tipo_medio(estacion: Estacion) -> str:
    return "TELEVISIÓN" if estacion.tipo_senal == "tv" else "RADIO"


# ── Estilos compartidos ──────────────────────────────────────────────────────────
_STYLES = getSampleStyleSheet()
_TITULO = ParagraphStyle("titulo", parent=_STYLES["Title"], fontSize=14, alignment=TA_CENTER)
_SUBTITULO = ParagraphStyle(
    "subtitulo", parent=_STYLES["Normal"], fontSize=11, alignment=TA_CENTER, spaceAfter=10
)
_ETIQUETA = ParagraphStyle("etiqueta", parent=_STYLES["Normal"], fontSize=9, textColor=colors.grey)
_VALOR = ParagraphStyle("valor", parent=_STYLES["Normal"], fontSize=10, spaceAfter=6)
_NOTA = ParagraphStyle(
    "nota", parent=_STYLES["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=4
)
_PIE = ParagraphStyle(
    "pie", parent=_STYLES["Normal"], fontSize=8, textColor=colors.grey, alignment=TA_RIGHT
)

_GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
)

# Filas de un registro por día, SIN cuadrícula vertical (a diferencia de `_GRID`): cada
# fila se separa de la siguiente con una sola línea horizontal delgada, igual al
# prototipo aprobado (`.pdf2-day-row { border-bottom: 1px solid #ddd }`).
_FILA_CON_LINEA = TableStyle(
    [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]
)


_FILA_PROGRAMADO = ParagraphStyle(
    "fila_programado", parent=_STYLES["Normal"], fontSize=9, leading=12
)


def _fila_dia_programado(dia: OrdenEstacionDia, programado: int) -> list:
    fecha_txt = (
        f"{_dia_semana(dia.fecha_transmision).capitalize()} {dia.fecha_transmision.day} "
        f"{MESES_ES[dia.fecha_transmision.month - 1]}, {dia.fecha_transmision.year}"
    )
    return [
        Paragraph(f"<b>{fecha_txt}</b>", _FILA_PROGRAMADO),
        Paragraph(f"Hora Inicio: <i>{_hora_12h(dia.hora_inicio)}</i>", _FILA_PROGRAMADO),
        Paragraph(f"Hora Término: <i>{_hora_12h(dia.hora_fin)}</i>", _FILA_PROGRAMADO),
        Paragraph(f"Pedidos: <i>{dia.spots_asignados}</i>", _FILA_PROGRAMADO),
        Paragraph(f"Asignados: <i>{programado}</i>", _FILA_PROGRAMADO),
    ]


def _proporciones(ancho_disponible: float, partes: list[float]) -> list[float]:
    total = sum(partes)
    return [ancho_disponible * p / total for p in partes]


def _campo(etiqueta: str, valor: str) -> list:
    return [Paragraph(etiqueta, _ETIQUETA), Paragraph(valor, _VALOR)]


_MARGEN_LATERAL = 1.8 * cm
_ANCHO_DISPONIBLE = letter[0] - 2 * _MARGEN_LATERAL


def _build(elementos: list) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=_MARGEN_LATERAL,
        rightMargin=_MARGEN_LATERAL,
    )
    doc.build(elementos)
    return buf.getvalue()


# ── PDF 1: Orden de servicio (2.1) ───────────────────────────────────────────────
def generar_pdf_servicio(db: Session, orden_estacion_id: uuid.UUID) -> bytes:
    ctx = _cargar_contexto(db, orden_estacion_id)
    oe, oc, estacion, plaza = ctx.oe, ctx.oc, ctx.estacion, ctx.plaza

    iva = (oe.importe_estacion * IVA_RATE).quantize(CENTAVOS)
    total = oe.importe_estacion + iva
    total_spots = sum(d.spots_asignados for d in ctx.dias)

    elementos: list = [
        _encabezado(
            ctx.empresa.nombre_empresa, "ORDEN DE SERVICIOS RADIOFÓNICOS", _ANCHO_DISPONIBLE
        ),
        Spacer(1, 10),
        Table(
            [[f"{estacion.nombre_estacion} ({estacion.frecuencia or '—'})", plaza.nombre_plaza]],
            colWidths=[10 * cm, 6 * cm],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ]
            ),
        ),
        Spacer(1, 10),
        Table(
            [
                _campo("Solicitud Orden", oc.numero_orden_cliente)
                + _campo("Duración", oe.duracion_spot),
                _campo("Agencia", ctx.agencia.nombre_agencia if ctx.agencia else "Venta directa")
                + _campo("Total de Spots", str(total_spots)),
                _campo("Anunciante", ctx.anunciante.nombre_comercial)
                + _campo("Precio Unitario", _moneda(oe.precio_spot)),
                _campo("Producto", oc.producto or "—")
                + _campo("Total de Días", str(len(ctx.dias))),
                ["", ""] + _campo("Importe", _moneda(oe.importe_estacion)),
                ["", ""] + _campo("I.V.A.", _moneda(iva)),
                ["", ""] + _campo("Total", _moneda(total)),
            ],
            colWidths=[3 * cm, 5 * cm, 3.5 * cm, 4.5 * cm],
        ),
        Spacer(1, 12),
        Paragraph("Periodo de Transmisión", ParagraphStyle("h2", parent=_STYLES["Heading3"])),
    ]

    filas = [["Día", "Fecha", "Inicio", "Término", "Spots Diarios", "Importe"]]
    for dia in ctx.dias:
        filas.append(
            [
                _dia_semana(dia.fecha_transmision).upper(),
                _fecha_corta(dia.fecha_transmision),
                dia.hora_inicio.strftime("%H:%M:%S"),
                dia.hora_fin.strftime("%H:%M:%S"),
                str(dia.spots_asignados),
                _moneda((Decimal(dia.spots_asignados) * oe.precio_spot).quantize(CENTAVOS)),
            ]
        )
    elementos.append(
        Table(
            filas, style=_GRID, colWidths=[2.5 * cm, 2.5 * cm, 2.3 * cm, 2.3 * cm, 3 * cm, 3 * cm]
        )
    )

    horarios = {(d.hora_inicio, d.hora_fin) for d in ctx.dias}
    if len(horarios) == 1:
        ini, fin = next(iter(horarios))
        elementos.append(Spacer(1, 8))
        elementos.append(
            Paragraph(
                f"<b>Horario de transmisión:</b> {ini.strftime('%H:%M')} A {fin.strftime('%H:%M')}",
                _VALOR,
            )
        )

    elementos.append(Spacer(1, 6))
    elementos.append(Paragraph(f"<b>Observaciones:</b> {oe.observaciones_estacion or '—'}", _VALOR))
    elementos.append(Spacer(1, 10))
    elementos.append(
        Paragraph(f"<b>Facturar al término de la pauta a {ctx.empresa.nombre_empresa}</b>", _VALOR)
    )
    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(f"{ctx.empresa.direccion_empresa or '—'} : {_generado_el()}", _PIE))

    return _build(elementos)


# ── PDF 2: Horarios programados (2.2) ────────────────────────────────────────────
def generar_pdf_programados(db: Session, orden_estacion_id: uuid.UUID) -> bytes:
    ctx = _cargar_contexto(db, orden_estacion_id)
    oe, oc, estacion, plaza = ctx.oe, ctx.oc, ctx.estacion, ctx.plaza
    if oe.estatus == EstatusOrdenEstacion.ASIGNADA.value:
        raise DomainError(
            "Aún no se han capturado los horarios programados de esta orden interna.",
            detalles={"estatus": oe.estatus},
        )

    letra = _letra_sufijo(oe.folio_orden_estacion)
    total_programado = sum(
        (d.spots_programados if d.spots_programados is not None else d.spots_asignados)
        for d in ctx.dias
    )

    elementos: list = [
        _encabezado(ctx.empresa.nombre_empresa, "HORARIOS PROGRAMADOS", _ANCHO_DISPONIBLE),
        Spacer(1, 10),
        Table(
            [
                _campo("Cliente", ctx.anunciante.nombre_comercial)
                + _campo("No. de Orden", f"{oc.numero_orden_cliente}/{letra}"),
                _campo("Campaña", oc.producto or "—") + _campo("Duración", oe.duracion_spot),
                _campo("Periodo", _rango_campania(oc))
                + _campo("Total Spots", str(total_programado)),
                _campo(
                    "Estación", f"{estacion.nombre_estacion} {estacion.frecuencia or ''}".strip()
                )
                + _campo("Ciudad", plaza.nombre_plaza),
            ],
            colWidths=[3 * cm, 6 * cm, 3 * cm, 4 * cm],
        ),
        Spacer(1, 12),
    ]

    filas = [
        _fila_dia_programado(
            dia,
            dia.spots_programados if dia.spots_programados is not None else dia.spots_asignados,
        )
        for dia in ctx.dias
    ]
    elementos.append(
        Table(
            filas,
            style=_FILA_CON_LINEA,
            colWidths=_proporciones(_ANCHO_DISPONIBLE, [1.7, 1.25, 1.25, 0.7, 0.75]),
        )
    )

    elementos.append(Spacer(1, 10))
    if oe.reporte_programados_ref:
        elementos.append(
            Paragraph(
                f"Reporte del afiliado adjunto: {_nombre_adjunto(oe.reporte_programados_ref)}",
                _NOTA,
            )
        )
    else:
        elementos.append(
            Paragraph(
                "Sin reporte detallado del afiliado adjunto. Para incluir el detalle de horarios "
                "específicos por spot, carga el archivo del afiliado desde la pantalla de captura "
                "de programados.",
                _NOTA,
            )
        )
    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(_generado_el(), _PIE))

    return _build(elementos)


# ── PDF 3: Horarios reales de transmisión (2.3) ──────────────────────────────────
def generar_pdf_reales(db: Session, orden_estacion_id: uuid.UUID) -> bytes:
    ctx = _cargar_contexto(db, orden_estacion_id)
    oe, oc, estacion, plaza = ctx.oe, ctx.oc, ctx.estacion, ctx.plaza
    if oe.estatus != EstatusOrdenEstacion.CERRADA.value:
        raise DomainError(
            "Aún no se han capturado los horarios reales de esta orden interna.",
            detalles={"estatus": oe.estatus},
        )

    verificaciones = {
        v.orden_estacion_dia_id: v
        for v in db.scalars(
            select(Verificacion).where(
                Verificacion.orden_estacion_dia_id.in_([d.orden_estacion_dia_id for d in ctx.dias])
            )
        )
    }
    total_real = sum(v.spots_verificados for v in verificaciones.values())

    elementos: list = [
        _encabezado(
            ctx.empresa.nombre_empresa, "HORARIOS REALES DE TRANSMISION", _ANCHO_DISPONIBLE
        ),
        Spacer(1, 10),
        Table(
            [
                _campo("Cliente", ctx.anunciante.nombre_comercial)
                + _campo("Periodo", f"DEL {_rango_campania(oc)}"),
                _campo("Campaña", oc.producto or "—")
                + _campo("Tipo de Medio", _tipo_medio(estacion)),
                _campo("Duración", oe.duracion_spot) + ["", ""],
                _campo("Emisora", f"{estacion.nombre_estacion} / {plaza.nombre_plaza}")
                + _campo("Total Spots Reales", str(total_real)),
            ],
            colWidths=[3 * cm, 6 * cm, 3.5 * cm, 3.5 * cm],
        ),
        Spacer(1, 12),
    ]

    filas = [["#", "Fecha", "Hora", "Spots", "Descripción", "Emisora"]]
    for i, dia in enumerate(ctx.dias, start=1):
        verificacion = verificaciones.get(dia.orden_estacion_dia_id)
        spots = verificacion.spots_verificados if verificacion else "—"
        filas.append(
            [
                str(i),
                _fecha_corta(dia.fecha_transmision),
                f"{_hora_24h(dia.hora_inicio)} - {_hora_24h(dia.hora_fin)}",
                str(spots),
                oc.producto or "—",
                estacion.nombre_estacion,
            ]
        )
    elementos.append(
        Table(
            filas, style=_GRID, colWidths=[1 * cm, 2.5 * cm, 2.8 * cm, 1.8 * cm, 5.5 * cm, 2.4 * cm]
        )
    )

    elementos.append(Spacer(1, 10))
    if oe.reporte_reales_ref:
        elementos.append(
            Paragraph(
                f"Reporte del afiliado adjunto: {_nombre_adjunto(oe.reporte_reales_ref)}", _NOTA
            )
        )
    else:
        elementos.append(
            Paragraph(
                "Detalle agregado por día. Para detalle por spot individual (hora exacta, track, "
                "ventana), carga el reporte del afiliado desde la pantalla de captura de reales.",
                _NOTA,
            )
        )
    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(_generado_el(), _PIE))

    return _build(elementos)


def _pdf_response(pdf: bytes, nombre_archivo: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


# ── Router ────────────────────────────────────────────────────────────────────
router_pdf = APIRouter(prefix="/estaciones", tags=["ordenes:estaciones:pdf"])


@router_pdf.get("/{item_id}/pdf/servicio")
def pdf_servicio_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    db: Session = Depends(get_db),
) -> Response:
    """PDF "Orden de servicio": tarifa, periodo asignado (2.1) e importe/IVA/total.
    Siempre disponible desde que la OE existe (no depende de 2.2/2.3)."""
    pdf = generar_pdf_servicio(db, item_id)
    return _pdf_response(pdf, "orden_de_servicio.pdf")


@router_pdf.get("/{item_id}/pdf/programados")
def pdf_programados_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    db: Session = Depends(get_db),
) -> Response:
    """PDF "Horarios programados": pedidos vs. confirmados por día (2.2). 400 si la OE
    todavía no avanzó a programados."""
    pdf = generar_pdf_programados(db, item_id)
    return _pdf_response(pdf, "horarios_programados.pdf")


@router_pdf.get("/{item_id}/pdf/reales")
def pdf_reales_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    db: Session = Depends(get_db),
) -> Response:
    """PDF "Horarios reales de transmisión": lo verificado por día (2.3). 400 si la OE
    todavía no avanzó a reales."""
    pdf = generar_pdf_reales(db, item_id)
    return _pdf_response(pdf, "horarios_reales.pdf")
