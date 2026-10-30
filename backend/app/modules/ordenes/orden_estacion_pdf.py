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
from collections.abc import Sequence
from dataclasses import dataclass
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
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.plaza import Plaza
from app.modules.ordenes.orden_cliente import OrdenCliente
from app.modules.ordenes.orden_estacion import (
    EstatusOrdenEstacion,
    OrdenEstacion,
    OrdenEstacionAudio,
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
    """Por defecto el nombre de empresa va grande y `subtitulo` chico debajo (ADR-089).
    "Horarios programados" (2.2) usa `subtitulo_primero=True` para igualar su PDF de
    referencia, donde el título del reporte va grande arriba y la empresa chica debajo —
    corrección puntual a ese reporte, no cambia servicio (2.1) ni reales (2.3).
    "Horarios reales" (2.3) usa `logo_grc=False`: su PDF de referencia no lleva el logo
    de Radio Centro, a diferencia de servicio y programados.
    "Horarios programados" también usa `logos_arriba=True`: en su referencia los logos
    van en su propio renglón, arriba del título — no centrados verticalmente junto al
    título/subtítulo como en servicio/reales (ADR-089)."""
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
        audios: list[OrdenEstacionAudio],
        marca: Marca | None,
    ) -> None:
        self.oe = oe
        self.oc = oc
        self.estacion = estacion
        self.plaza = plaza
        self.anunciante = anunciante
        self.agencia = agencia
        self.empresa = empresa
        self.dias = dias
        self.audios = audios
        # ADR-193 (petición del usuario): la Marca no se cargaba en el contexto de los
        # PDFs — `None` si la OC no capturó marca (campo opcional, `oc.marca_id`).
        self.marca = marca


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
    marca = db.get(Marca, oc.marca_id) if oc and oc.marca_id else None
    if oc is None or estacion is None or plaza is None or anunciante is None or empresa is None:
        raise NotFoundError("Faltan datos relacionados de la OrdenEstacion para generar el PDF.")
    dias = list(
        db.scalars(
            select(OrdenEstacionDia)
            .where(OrdenEstacionDia.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionDia.fecha_transmision)
        )
    )
    audios = list(
        db.scalars(
            select(OrdenEstacionAudio)
            .where(OrdenEstacionAudio.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionAudio.orden)
        )
    )
    return _Contexto(oe, oc, estacion, plaza, anunciante, agencia, empresa, dias, audios, marca)


def _rango_campania(oc: OrdenCliente) -> str:
    return f"{_fecha_larga(oc.fecha_inicio_campania)} AL {_fecha_larga(oc.fecha_fin_campania)}"


def _tipo_medio(estacion: Estacion) -> str:
    return "TELEVISIÓN" if estacion.tipo_senal == "tv" else "RADIO"


def _descripcion_estacion(estacion: Estacion) -> str:
    """"Siglas Frecuencia TIPO Nombre" — mismo formato que ya usa el front para
    identificar la estación en sus selectores (ADR-136/ADR-191). Petición del usuario
    2026-10-30: "Horarios programados" (2.2) y "Horarios reales" (2.3) mostraban solo
    nombre + frecuencia, sin siglas ni tipo de señal. Cualquier parte vacía (siglas
    faltantes, p.ej.) se OMITE en vez de dejar un espacio en blanco de más."""
    partes = [
        estacion.siglas,
        estacion.frecuencia,
        estacion.tipo_senal.upper() if estacion.tipo_senal else None,
        estacion.nombre_estacion,
    ]
    return " ".join(p for p in partes if p)


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

# Campos de "Horarios reales" (2.3): etiqueta en negritas, valor SIN negritas (ADR-194,
# petición del usuario — antes el valor también iba en negritas, igual al PDF de
# referencia original; a diferencia de `_campo()`, la etiqueta aquí va en negro, no gris).
_CAMPO_NEGRITA = ParagraphStyle(
    "campo_negrita", parent=_STYLES["Normal"], fontSize=9.5, textColor=colors.black, spaceAfter=4
)


def _campo_negrita(etiqueta: str, valor: str) -> list:
    return [
        Paragraph(f"<b>{etiqueta}:</b>", _CAMPO_NEGRITA),
        Paragraph(valor, _CAMPO_NEGRITA),
    ]


# Columna derecha de "reales" (ADR-058): mismo criterio que `_campo_der()` de "servicio" —
# el valor va justificado a la derecha, para que ocupe todo el ancho del recuadro.
_CAMPO_NEGRITA_DER = ParagraphStyle("campo_negrita_der", parent=_CAMPO_NEGRITA, alignment=TA_RIGHT)


def _campo_negrita_der(etiqueta: str, valor: str) -> list:
    return [
        Paragraph(f"<b>{etiqueta}:</b>", _CAMPO_NEGRITA),
        Paragraph(valor, _CAMPO_NEGRITA_DER),
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


def _nombre_material(dia: OrdenEstacionDia, audios: list[OrdenEstacionAudio]) -> str | None:
    """Nombre del material asignado a ESTE spot (ADR-187: 1 material por spot, ya no un
    solo default compartido para todo el día) — `None` si este día no tiene ningún
    `orden_estacion_audio_id` propio (p.ej. datos sembrados antes de ADR-187) o el audio
    referenciado ya no existe."""
    if dia.orden_estacion_audio_id:
        coincidencia = next(
            (a for a in audios if a.orden_estacion_audio_id == dia.orden_estacion_audio_id), None
        )
        if coincidencia:
            return coincidencia.nombre_archivo
    return None


@dataclass
class _GrupoFechaDia:
    """ADR-196 (corrige un bug real): agrupado de TODAS las filas reales de una misma
    fecha (1 por spot, ADR-127) — mismo criterio que `agruparPorFecha` del frontend
    (`PeriodoTransmisionGrid.tsx`, ADR-185): Hora Inicio = la más temprana del grupo,
    Hora Fin = la más tardía, Spots = la suma. `dias` conserva las filas reales (para
    resolver los materiales del día en el PDF de Programados). Usado por los PDFs de
    Servicio y Programados — "Capturar reales" y el PDF de Reales NO se agrupan, siguen
    mostrando 1 renglón por spot como siempre."""

    fecha: date
    hora_inicio: time
    hora_fin: time
    spots: int
    dias: list[OrdenEstacionDia]
    cancelada: bool


def _agrupar_dias_por_fecha(dias: Sequence[OrdenEstacionDia]) -> list[_GrupoFechaDia]:
    por_fecha: dict[date, list[OrdenEstacionDia]] = {}
    for d in dias:
        por_fecha.setdefault(d.fecha_transmision, []).append(d)
    grupos: list[_GrupoFechaDia] = []
    for fecha, filas in por_fecha.items():
        cancelada = all(f.cancelada for f in filas)
        # Si TODAS están canceladas no hay "activas" que agregar — se usan todas para no
        # quedarse sin horario/spots que mostrar (mismo criterio que el frontend).
        base = filas if cancelada else [f for f in filas if not f.cancelada]
        grupos.append(
            _GrupoFechaDia(
                fecha=fecha,
                hora_inicio=min(f.hora_inicio for f in base),
                hora_fin=max(f.hora_fin for f in base),
                spots=sum(f.spots_asignados for f in base),
                dias=filas,
                cancelada=cancelada,
            )
        )
    return sorted(grupos, key=lambda g: g.fecha)


def _materiales_grupo(grupo: _GrupoFechaDia, audios: list[OrdenEstacionAudio]) -> str:
    """ADR-196 (petición del usuario): "Material a Transmitir" lista TODOS los
    materiales distintos usados ese día (1 por spot, ADR-187), separados por coma, en el
    orden en que le tocó a cada spot (por `hora_inicio`) — ya no un solo nombre."""
    if not audios:
        return "—"
    filas_ordenadas = sorted(grupo.dias, key=lambda d: d.hora_inicio)
    nombres: list[str] = []
    for dia in filas_ordenadas:
        nombre = _nombre_material(dia, audios)
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return ", ".join(nombres) if nombres else "—"


def _fila_dia_programado(grupo: _GrupoFechaDia, nombre_material: str) -> list:
    fecha_txt = (
        f"{_dia_semana(grupo.fecha).capitalize()} {grupo.fecha.day} "
        f"{MESES_ES[grupo.fecha.month - 1]}, {grupo.fecha.year}"
    )
    # ADR-192 (petición del usuario, corrige un bug real): ADR-118 había colapsado
    # "Horario" a un solo valor, asumiendo `hora_inicio == hora_fin` siempre (ADR-108) —
    # supuesto inválido desde ADR-184 en adelante. Vuelve a mostrar el rango completo.
    # ADR-196: `grupo` reemplaza la fila real suelta — ya viene agrupada por fecha.
    # ADR-221c (petición del usuario): faltaba el número de spots DE ESE DÍA (solo se veía
    # el total agregado arriba, "TOTAL SPOTS") — se agrega como columna propia.
    return [
        Paragraph(f"<b>{fecha_txt}</b>", _FILA_PROGRAMADO),
        Paragraph(
            f"Horario: <i>{_hora_12h(grupo.hora_inicio)} A {_hora_12h(grupo.hora_fin)}</i>",
            _FILA_PROGRAMADO,
        ),
        Paragraph(f"Spots: <i>{grupo.spots}</i>", _FILA_PROGRAMADO),
        Paragraph(f"Material a Transmitir: <i>{nombre_material}</i>", _FILA_PROGRAMADO),
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
    # El contenido arranca pegado al margen superior en los 3 reportes (corrección
    # posterior a ADR-057: el centrado vertical dejaba un espacio en blanco demasiado
    # grande arriba cuando el contenido era corto, p. ej. una orden de un solo día).
    doc.build(elementos)
    return buf.getvalue()


# ── PDF 1: Orden de servicio (2.1) ───────────────────────────────────────────────
def generar_pdf_servicio(db: Session, orden_estacion_id: uuid.UUID) -> bytes:
    ctx = _cargar_contexto(db, orden_estacion_id)
    oe, oc, estacion, plaza = ctx.oe, ctx.oc, ctx.estacion, ctx.plaza

    iva = (oe.importe_estacion * IVA_RATE).quantize(CENTAVOS)
    total = oe.importe_estacion + iva
    # ADR-196 (corrige un bug real): la tabla de días se agrupa por fecha — "Total de
    # Spots"/"Total de Días" se derivan del mismo agrupado (no de `ctx.dias` crudo, 1
    # fila por spot) para que el pie coincida con la suma de los renglones que se ven.
    grupos_dias = _agrupar_dias_por_fecha(ctx.dias)
    total_spots = sum(g.spots for g in grupos_dias)

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
    # ADR-193 (petición del usuario): se agregan "Marca" y "Producto" — antes "Producto"
    # en realidad mostraba `oc.producto` (texto libre, la CAMPAÑA), y el Producto de
    # verdad (`oe.producto_tarifa`, del catálogo F0-06, conectado por ADR-166/169) no
    # aparecía en ningún PDF. "Producto"/"Campaña" quedan como 2 campos DISTINTOS.
    tabla_campos = Table(
        [
            _campo("Solicitud Orden", oc.numero_orden_cliente)
            + _campo_der("Duración", oe.duracion_spot),
            _campo("Agencia", ctx.agencia.nombre_agencia if ctx.agencia else "Venta directa")
            + _campo_der("Total de Spots", str(total_spots)),
            _campo("Anunciante", ctx.anunciante.nombre_comercial)
            + _campo_der("Precio Unitario", _moneda(oe.precio_spot)),
            _campo("Campaña", oc.producto or "—")
            + _campo_der("Total de Días", str(len(grupos_dias))),
            _campo("Marca", ctx.marca.nombre_marca if ctx.marca else "—")
            + _campo_der("Importe", _moneda(oe.importe_estacion)),
            _campo("Producto", oe.producto_tarifa or "—") + _campo_der("I.V.A.", _moneda(iva)),
            ["", ""] + _campo_der("Total", _moneda(total)),
        ],
        colWidths=_proporciones(_ANCHO_MARCO_INTERNO, [3, 5, 3.5, 4.5]),
    )

    # ADR-192 (petición del usuario, corrige un bug real): ADR-155 había consolidado
    # "Inicio"/"Término" en una sola columna "Horario de Transmisión", asumiendo que
    # `hora_inicio`/`hora_fin` se capturaban siempre iguales (ADR-108/118) — ese supuesto
    # dejó de valer desde ADR-184 en adelante (la captura web volvió a un rango real).
    # Vuelve a ser 2 columnas, "Hora Inicio"/"Hora Fin".
    # ADR-196 (corrige un bug real): 1 renglón por FECHA (`grupos_dias`), no 1 por spot —
    # mismo criterio que la grid de captura (ADR-185).
    filas = [["Día", "Fecha", "Hora Inicio", "Hora Fin", "Spots Diarios", "Importe"]]
    for grupo in grupos_dias:
        filas.append(
            [
                _dia_semana(grupo.fecha).upper(),
                _fecha_corta(grupo.fecha),
                grupo.hora_inicio.strftime("%H:%M:%S"),
                grupo.hora_fin.strftime("%H:%M:%S"),
                str(grupo.spots),
                _moneda((Decimal(grupo.spots) * oe.precio_spot).quantize(CENTAVOS)),
            ]
        )
    tabla_dias = Table(
        filas, style=_GRID, colWidths=[2.5 * cm, 2.5 * cm, 2.3 * cm, 2.3 * cm, 3 * cm, 3 * cm]
    )

    # ADR-131 (corrige un bug real): `tabla_dias` YA NO va anidada dentro de la celda de
    # `marco` — con ADR-127 (varios spots por día) esta tabla puede crecer a muchas más
    # filas que antes (un renglón por spot, no por día), y una tabla anidada dentro de la
    # celda de OTRA tabla NO puede partirse entre páginas en reportlab: si el contenido de
    # esa celda no cabe completo en lo que queda de una página, truena con
    # `LayoutError` ("too large ... in frame") en vez de continuar en la siguiente. El
    # marco (borde) ahora envuelve SOLO el encabezado (`tabla_estacion_plaza` +
    # `tabla_campos`, tamaño fijo, nunca crece con el número de días) — `tabla_dias` y el
    # resto del contenido van como flowables de nivel superior, igual que ya hacían
    # `generar_pdf_programados`/`generar_pdf_reales`, que sí paginan sin problema.
    marco = Table(
        [[tabla_estacion_plaza], [[tabla_campos]]],
        colWidths=[_ANCHO_DISPONIBLE],
        style=_MARCO,
    )

    elementos: list = [
        _encabezado(
            ctx.empresa.nombre_empresa, "ORDEN DE SERVICIOS RADIOFÓNICOS", _ANCHO_DISPONIBLE
        ),
        Spacer(1, 10),
        marco,
        Spacer(1, 12),
        Paragraph("Periodo de Transmisión", ParagraphStyle("h2", parent=_STYLES["Heading3"])),
        Spacer(1, 6),
        tabla_dias,
    ]

    # ADR-196: compara los GRUPOS por fecha, no las filas reales sueltas — con éstas,
    # el mismo día ya trae varios `hora_inicio` distintos (1 por spot, ADR-127) y este
    # resumen casi nunca hubiera coincidido, aunque todos los días compartan rango.
    horarios = {(g.hora_inicio, g.hora_fin) for g in grupos_dias}
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
    elementos.append(
        Paragraph(
            f'<font color="red"><b>Observaciones:</b></font> {oe.observaciones_estacion or "—"}',
            _VALOR,
        )
    )
    elementos.append(Spacer(1, 10))
    elementos.append(
        Paragraph(f"<b>Facturar al término de la pauta a {ctx.empresa.nombre_empresa}</b>", _VALOR)
    )
    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(ctx.empresa.direccion_empresa or "—", _PIE_IZQUIERDA))

    return _build(elementos)


# ── PDF 2: Horarios programados (2.2) ────────────────────────────────────────────
def generar_pdf_programados(db: Session, orden_estacion_id: uuid.UUID) -> bytes:
    # ADR-121: ya no se rechaza en 'asignada' — los horarios/spots "programados" se
    # capturan desde el alta (fallback a `spots_asignados`, ver `avanzar_reales`), así
    # que este PDF está listo desde que la OE existe.
    ctx = _cargar_contexto(db, orden_estacion_id)
    oe, oc, estacion, plaza = ctx.oe, ctx.oc, ctx.estacion, ctx.plaza

    letra = _letra_sufijo(oe.folio_orden_estacion)
    total_programado = sum(
        (d.spots_programados if d.spots_programados is not None else d.spots_asignados)
        for d in ctx.dias
    )

    nombre_estacion_ciudad = _descripcion_estacion(estacion)

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
        # ADR-193 (petición del usuario): "MARCA"/"PRODUCTO" no aparecían en ningún PDF —
        # "PRODUCTO" aquí es `oe.producto_tarifa` (catálogo F0-06), DISTINTO de "CAMPAÑA"
        # (`oc.producto`, texto libre) de la línea anterior.
        Paragraph(
            f"<b>MARCA :</b> {(ctx.marca.nombre_marca if ctx.marca else '—').upper()} &nbsp;&nbsp; "
            f"<b>PRODUCTO :</b> {(oe.producto_tarifa or '—').upper()}",
            _CAMPO_LINEA,
        ),
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
        _fila_dia_programado(grupo, _materiales_grupo(grupo, ctx.audios))
        for grupo in _agrupar_dias_por_fecha(ctx.dias)
    ]
    elementos.append(
        Table(
            filas,
            style=_FILA_CON_LINEA,
            colWidths=_proporciones(_ANCHO_DISPONIBLE, [1.4, 1.1, 0.7, 2.3]),
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
                # ADR-193 (petición del usuario): "MARCA"/"PRODUCTO" no aparecían — ambos
                # campos distintos de "CAMPAÑA" (de arriba, `oc.producto` libre): MARCA
                # es `ctx.marca`, PRODUCTO es `oe.producto_tarifa` (catálogo F0-06).
                _campo_negrita("DURACION", oe.duracion_spot)
                + _campo_negrita_der(
                    "MARCA", (ctx.marca.nombre_marca if ctx.marca else "—").upper()
                ),
                _campo_negrita(
                    "EMISORA", f"{_descripcion_estacion(estacion)} / {plaza.nombre_plaza}".upper()
                )
                + _campo_negrita_der("TOTAL SPOTS REALES", str(total_real)),
                _campo_negrita("PRODUCTO", (oe.producto_tarifa or "—").upper()) + ["", ""],
            ],
            colWidths=_proporciones(_ANCHO_DISPONIBLE, [3, 6, 3.5, 3.5]),
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]),
        ),
        Spacer(1, 12),
    ]

    # ADR-196 (corrige un bug real de ADR-192, petición del usuario): "HORA" vuelve a
    # mostrar UN SOLO horario — `hora_inicio`, el punto real de ESE spot — no un rango
    # `inicio - fin`. Desde ADR-186, `hora_fin` es el fin de rango COMPARTIDO entre todos
    # los spots del mismo día (no algo propio de este renglón en particular), así que
    # mostrarlo aquí como rango confundía más de lo que aclaraba — "Capturar reales"
    # sigue siendo por spot, SIN agrupar (a diferencia de Servicio/Programados, ADR-196).
    # ADR-221c (petición del usuario, corrige un bug real): se quita la columna "SPOTS" de
    # este detalle — cada renglón YA es un solo spot (ADR-127), así que siempre mostraba
    # "1" (o "—"), sin aportar nada; ese conteo tiene sentido agrupado por día, no aquí —
    # ver el nuevo "Spots" por día que sí se agregó al PDF de Programados.
    filas = [["", "FECHA", "HORA", "DESCRIPCION", "EMISORA"]]
    descripcion_estacion = _descripcion_estacion(estacion).upper()
    for i, dia in enumerate(ctx.dias, start=1):
        filas.append(
            [
                str(i),
                _fecha_corta(dia.fecha_transmision),
                _hora_24h(dia.hora_inicio),
                Paragraph((oc.producto or "—").upper(), _FILA_REALES),
                Paragraph(descripcion_estacion, _FILA_REALES),
            ]
        )
    elementos.append(
        Table(
            filas,
            style=_TABLA_SIN_MARCO,
            colWidths=[1 * cm, 2.5 * cm, 2.8 * cm, 8.6 * cm, 2.9 * cm],
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
