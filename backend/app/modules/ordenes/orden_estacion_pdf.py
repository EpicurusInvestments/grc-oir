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
from datetime import date, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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


def _encabezado(
    nombre_empresa: str,
    subtitulo: str,
    ancho_disponible: float,
    *,
    subtitulo_primero: bool = False,
    logo_grc: bool = True,
    logos_arriba: bool = False,
) -> Table:
    """Por defecto el nombre de empresa va grande y `subtitulo` chico debajo (ADR-044).
    "Horarios programados" (2.2) usa `subtitulo_primero=True` para igualar su PDF de
    referencia, donde el título del reporte va grande arriba y la empresa chica debajo —
    corrección puntual a ese reporte, no cambia servicio (2.1) ni reales (2.3).
    "Horarios reales" (2.3) usa `logo_grc=False`: su PDF de referencia no lleva el logo
    de Radio Centro, a diferencia de servicio y programados.
    "Horarios programados" también usa `logos_arriba=True`: en su referencia los logos
    van en su propio renglón, arriba del título — no centrados verticalmente junto al
    título/subtítulo como en servicio/reales (ADR-044)."""
    grande, chico = (subtitulo, nombre_empresa) if subtitulo_primero else (nombre_empresa, subtitulo)
    ancho_logo_col = 3.5 * cm
    logo_derecho = _logo_flowable("grc") if logo_grc else Spacer(1, _LOGO_ALTO)
    titulo_bloque = [Paragraph(grande, _TITULO), Paragraph(chico, _SUBTITULO)]
    if logos_arriba:
        data = [
            [_logo_flowable("oir"), "", logo_derecho],
            ["", titulo_bloque, ""],
        ]
    else:
        data = [[_logo_flowable("oir"), titulo_bloque, logo_derecho]]
    tabla = Table(
        data,
        colWidths=[ancho_logo_col, ancho_disponible - 2 * ancho_logo_col, ancho_logo_col],
    )
    tabla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("TOPPADDING", (1, -1), (1, -1), 6 if logos_arriba else 0),
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
# Pie de "Orden de servicio" (2.1): a diferencia de `_PIE`, va justificado a la izquierda
# (corrección puntual contra el PDF de referencia — programados/reales no cambian).
_PIE_IZQUIERDA = ParagraphStyle("pie_izquierda", parent=_PIE, alignment=TA_LEFT)

# Marco completo de "Orden de servicio" (2.1): envuelve estación/plaza + campos + tabla
# de días en un solo recuadro, igual al PDF de referencia (programados/reales no llevan
# este marco — cada uno conserva su propio estilo de tabla).
#
# 2 filas, no 1: la fila 0 (estación/plaza) va SIN padding propio para que su línea
# inferior (ADR-058-bis) llegue exactamente a los bordes izquierdo/derecho del marco —
# con padding habría un hueco entre esa línea y el borde. La fila 1 (el resto del
# contenido) conserva el padding original de 8pt.
_MARCO = TableStyle(
    [
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (0, 1), (0, 1), 8),
        ("RIGHTPADDING", (0, 1), (0, 1), 8),
        ("TOPPADDING", (0, 1), (0, 1), 8),
        ("BOTTOMPADDING", (0, 1), (0, 1), 8),
    ]
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

# Líneas de campo de "Horarios programados" (2.2): etiqueta en negro (no gris como
# `_ETIQUETA`) seguida del valor en la misma línea — igual al PDF de referencia, que no
# usa el formato de 2 columnas etiqueta-arriba/valor-abajo de `_campo()`.
_CAMPO_LINEA = ParagraphStyle(
    "campo_linea", parent=_STYLES["Normal"], fontSize=9.5, textColor=colors.black, spaceAfter=4
)
_CAMPO_LINEA_DER = ParagraphStyle("campo_linea_der", parent=_CAMPO_LINEA, alignment=TA_RIGHT)

# Campos de "Horarios reales" (2.3): etiqueta Y valor en negritas (a diferencia de
# `_campo()`, que deja la etiqueta en gris) — igual al PDF de referencia.
_CAMPO_NEGRITA = ParagraphStyle(
    "campo_negrita", parent=_STYLES["Normal"], fontSize=9.5, textColor=colors.black, spaceAfter=4
)


def _campo_negrita(etiqueta: str, valor: str) -> list:
    return [
        Paragraph(f"<b>{etiqueta}:</b>", _CAMPO_NEGRITA),
        Paragraph(f"<b>{valor}</b>", _CAMPO_NEGRITA),
    ]


# Columna derecha de "reales" (ADR-058): mismo criterio que `_campo_der()` de "servicio" —
# el valor va justificado a la derecha, para que ocupe todo el ancho del recuadro.
_CAMPO_NEGRITA_DER = ParagraphStyle("campo_negrita_der", parent=_CAMPO_NEGRITA, alignment=TA_RIGHT)


def _campo_negrita_der(etiqueta: str, valor: str) -> list:
    return [
        Paragraph(f"<b>{etiqueta}:</b>", _CAMPO_NEGRITA),
        Paragraph(f"<b>{valor}</b>", _CAMPO_NEGRITA_DER),
    ]


# Tabla de "Horarios reales" (2.3): SIN cuadrícula (a diferencia de `_GRID`) — solo una
# línea bajo el encabezado, igual al PDF de referencia.
_TABLA_SIN_MARCO = TableStyle(
    [
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
)

# DESCRIPCION/EMISORA de "Horarios reales" (2.3) van en `Paragraph`, no como texto plano:
# una celda de tabla de reportlab NO envuelve un `str` dentro del ancho de columna, así que
# una campaña o nombre de estación largos se salían de su columna y se encimaban con la
# siguiente. `Paragraph` sí hace word-wrap dentro de `colWidths`.
_FILA_REALES = ParagraphStyle("fila_reales", parent=_STYLES["Normal"], fontSize=9, leading=11)


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


# Columna derecha de "servicio"/"reales" (ADR-058): el valor va justificado A LA DERECHA,
# igual que su referencia real — con la fila de estación/plaza (ADR-057) ocupando ya todo
# el ancho del recuadro, dejar el valor pegado a la etiqueta se veía descentrado.
_VALOR_DER = ParagraphStyle("valor_der", parent=_VALOR, alignment=TA_RIGHT)


def _campo_der(etiqueta: str, valor: str) -> list:
    return [Paragraph(etiqueta, _ETIQUETA), Paragraph(valor, _VALOR_DER)]


_MARGEN_LATERAL = 1.8 * cm
_ANCHO_DISPONIBLE = letter[0] - 2 * _MARGEN_LATERAL
_MARGEN_VERTICAL = 1.5 * cm
# `_MARCO` (servicio) le pone 8pt de LEFTPADDING/RIGHTPADDING a su única celda — el ancho
# real que le queda a lo que va DENTRO del marco es este, no `_ANCHO_DISPONIBLE` completo.
_ANCHO_MARCO_INTERNO = _ANCHO_DISPONIBLE - 16


def _altura_contenido(elementos: list, ancho: float) -> float:
    """Suma el alto que ocupará cada flowable, para poder centrar el recuadro
    verticalmente en la hoja (ADR-057). `wrap()` es la forma estándar de reportlab de
    medir un flowable sin dibujarlo — es seguro llamarlo aquí y que `doc.build()` lo
    vuelva a llamar después con el mismo ancho."""
    alto_holgado = 10_000  # alto "de sobra": que nada calcule un salto de página al medir
    return sum(el.wrap(ancho, alto_holgado)[1] for el in elementos)


def _build(elementos: list) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=_MARGEN_VERTICAL,
        bottomMargin=_MARGEN_VERTICAL,
        leftMargin=_MARGEN_LATERAL,
        rightMargin=_MARGEN_LATERAL,
    )
    alto_disponible = letter[1] - 2 * _MARGEN_VERTICAL
    alto_contenido = _altura_contenido(elementos, _ANCHO_DISPONIBLE)
    relleno = max(0.0, (alto_disponible - alto_contenido) / 2)
    # Si el contenido no cabe en una hoja (relleno = 0), fluye normal y pagina como
    # siempre — el centrado solo aplica cuando sobra espacio.
    doc.build([Spacer(1, relleno), *elementos] if relleno else elementos)
    return buf.getvalue()


# ── PDF 1: Orden de servicio (2.1) ───────────────────────────────────────────────
def generar_pdf_servicio(db: Session, orden_estacion_id: uuid.UUID) -> bytes:
    ctx = _cargar_contexto(db, orden_estacion_id)
    oe, oc, estacion, plaza = ctx.oe, ctx.oc, ctx.estacion, ctx.plaza

    iva = (oe.importe_estacion * IVA_RATE).quantize(CENTAVOS)
    total = oe.importe_estacion + iva
    total_spots = sum(d.spots_asignados for d in ctx.dias)

    tabla_estacion_plaza = Table(
        [[f"{estacion.nombre_estacion} ({estacion.frecuencia or '—'})", plaza.nombre_plaza]],
        colWidths=_proporciones(_ANCHO_DISPONIBLE, [10, 6]),
        style=TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                # Solo una línea ABAJO para separar la fila de identificación estación/plaza
                # del resto de los campos (ADR-058-bis) — no un recuadro propio con las 4
                # líneas: al ocupar ya todo el ancho interno del marco (ADR-058), esa línea
                # queda a ras de los bordes del marco exterior, como una sola pieza.
                ("LINEBELOW", (0, 0), (-1, -1), 1, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )
    tabla_campos = Table(
        [
            _campo("Solicitud Orden", oc.numero_orden_cliente)
            + _campo_der("Duración", oe.duracion_spot),
            _campo("Agencia", ctx.agencia.nombre_agencia if ctx.agencia else "Venta directa")
            + _campo_der("Total de Spots", str(total_spots)),
            _campo("Anunciante", ctx.anunciante.nombre_comercial)
            + _campo_der("Precio Unitario", _moneda(oe.precio_spot)),
            _campo("Producto", oc.producto or "—")
            + _campo_der("Total de Días", str(len(ctx.dias))),
            ["", ""] + _campo_der("Importe", _moneda(oe.importe_estacion)),
            ["", ""] + _campo_der("I.V.A.", _moneda(iva)),
            ["", ""] + _campo_der("Total", _moneda(total)),
        ],
        colWidths=_proporciones(_ANCHO_MARCO_INTERNO, [3, 5, 3.5, 4.5]),
    )

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
    tabla_dias = Table(
        filas, style=_GRID, colWidths=[2.5 * cm, 2.5 * cm, 2.3 * cm, 2.3 * cm, 3 * cm, 3 * cm]
    )

    contenido_marco: list = [
        tabla_campos,
        Spacer(1, 12),
        Paragraph("Periodo de Transmisión", ParagraphStyle("h2", parent=_STYLES["Heading3"])),
        Spacer(1, 6),
        tabla_dias,
    ]

    horarios = {(d.hora_inicio, d.hora_fin) for d in ctx.dias}
    if len(horarios) == 1:
        ini, fin = next(iter(horarios))
        contenido_marco.append(Spacer(1, 8))
        contenido_marco.append(
            Paragraph(
                f"<b>Horario de transmisión:</b> {ini.strftime('%H:%M')} A {fin.strftime('%H:%M')}",
                _VALOR,
            )
        )

    contenido_marco.append(Spacer(1, 6))
    contenido_marco.append(
        Paragraph(
            f'<font color="red"><b>Observaciones:</b></font> {oe.observaciones_estacion or "—"}',
            _VALOR,
        )
    )
    contenido_marco.append(Spacer(1, 10))
    contenido_marco.append(
        Paragraph(f"<b>Facturar al término de la pauta a {ctx.empresa.nombre_empresa}</b>", _VALOR)
    )
    contenido_marco.append(Spacer(1, 20))
    contenido_marco.append(Paragraph(ctx.empresa.direccion_empresa or "—", _PIE_IZQUIERDA))

    marco = Table(
        [[tabla_estacion_plaza], [contenido_marco]],
        colWidths=[_ANCHO_DISPONIBLE],
        style=_MARCO,
    )

    elementos: list = [
        _encabezado(
            ctx.empresa.nombre_empresa, "ORDEN DE SERVICIOS RADIOFÓNICOS", _ANCHO_DISPONIBLE
        ),
        Spacer(1, 10),
        marco,
    ]

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

    nombre_estacion_ciudad = f"{estacion.nombre_estacion} {estacion.frecuencia or ''}".strip()

    elementos: list = [
        _encabezado(
            ctx.empresa.nombre_empresa,
            "HORARIOS PROGRAMADOS",
            _ANCHO_DISPONIBLE,
            subtitulo_primero=True,
            logos_arriba=True,
        ),
        Spacer(1, 10),
        Paragraph(f"<b>CLIENTE :</b> {ctx.anunciante.nombre_comercial.upper()}", _CAMPO_LINEA),
        Paragraph(f"<b>CAMPAÑA :</b> {(oc.producto or '—').upper()}", _CAMPO_LINEA),
        Paragraph(
            f"<b>No. DE ORDEN :</b> {oc.numero_orden_cliente}/{letra} &nbsp;&nbsp; "
            f"<b>DURACION:</b> {oe.duracion_spot} &nbsp;/&nbsp; "
            f"<b>PERIODO :</b> {_rango_campania(oc)}",
            _CAMPO_LINEA,
        ),
        Table(
            [
                [
                    Paragraph(
                        f"<b>ESTACION:</b> {nombre_estacion_ciudad} / "
                        f"<b>CIUDAD:</b> {plaza.nombre_plaza.upper()}",
                        _CAMPO_LINEA,
                    ),
                    Paragraph(f"<b>TOTAL SPOTS</b> &nbsp;&nbsp;{total_programado}", _CAMPO_LINEA_DER),
                ]
            ],
            colWidths=[_ANCHO_DISPONIBLE * 0.7, _ANCHO_DISPONIBLE * 0.3],
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
            ctx.empresa.nombre_empresa,
            "HORARIOS REALES DE TRANSMISION",
            _ANCHO_DISPONIBLE,
            logo_grc=False,
            logos_arriba=True,
        ),
        Spacer(1, 10),
        Table(
            [
                _campo_negrita("CLIENTE", ctx.anunciante.nombre_comercial.upper())
                + _campo_negrita_der("PERIODO", f"DEL {_rango_campania(oc)}"),
                _campo_negrita("CAMPAÑA", (oc.producto or "—").upper())
                + _campo_negrita_der("TIPO DE MEDIO", _tipo_medio(estacion)),
                _campo_negrita("DURACION", oe.duracion_spot) + ["", ""],
                _campo_negrita("EMISORA", f"{estacion.nombre_estacion} / {plaza.nombre_plaza}".upper())
                + _campo_negrita_der("TOTAL SPOTS REALES", str(total_real)),
            ],
            colWidths=_proporciones(_ANCHO_DISPONIBLE, [3, 6, 3.5, 3.5]),
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]),
        ),
        Spacer(1, 12),
    ]

    filas = [["", "FECHA", "HORA", "SPOTS", "DESCRIPCION", "EMISORA"]]
    for i, dia in enumerate(ctx.dias, start=1):
        verificacion = verificaciones.get(dia.orden_estacion_dia_id)
        spots = verificacion.spots_verificados if verificacion else "—"
        filas.append(
            [
                str(i),
                _fecha_corta(dia.fecha_transmision),
                f"{_hora_24h(dia.hora_inicio)} - {_hora_24h(dia.hora_fin)}",
                str(spots),
                Paragraph((oc.producto or "—").upper(), _FILA_REALES),
                Paragraph(estacion.nombre_estacion.upper(), _FILA_REALES),
            ]
        )
    elementos.append(
        Table(
            filas,
            style=_TABLA_SIN_MARCO,
            colWidths=[1 * cm, 2.5 * cm, 2.8 * cm, 1.8 * cm, 6.8 * cm, 2.9 * cm],
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
