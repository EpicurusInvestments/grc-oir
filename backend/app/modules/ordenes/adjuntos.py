"""Adjuntos de Órdenes (ODC, carta de conciliación, reportes de afiliado).

Antes "simulados" en el frontend (solo se capturaba el nombre del archivo, nunca se
subía nada). Un solo endpoint genérico de subida/descarga para los 5 campos que lo
necesitan (`OrdenCliente.odc_pdf_ref`, `odc_cerrada_ref`, `carta_conciliacion_ref`,
`OrdenEstacion.reporte_reales_ref`, `reporte_programados_ref`) — todos son columnas de
texto que ya existían como referencia simulada; ahora guardan la CLAVE real en el
almacenamiento (S3 o local, según `STORAGE_BACKEND`, mismo bucket que los adjuntos de
Contrato — ADR-027 — bajo un prefijo propio para no mezclarlos).

El bucket es PRIVADO: el archivo se sirve SIEMPRE por este endpoint, nunca por URL
pública directa (mismo criterio que Contrato).

Construido con `build_adjuntos_router` (`app/shared/adjuntos_router.py`, extraída en
F3): `content_disposition="inline"` (se previsualiza) y SÍ quita el prefijo UUID de la
clave al mostrar el nombre de descarga — el par de detalles que distingue a este router
del de `facturacion/adjuntos.py`.
"""

from __future__ import annotations

from enum import StrEnum

from app.shared.adjuntos_router import build_adjuntos_router


class TipoAdjuntoOrden(StrEnum):
    ODC = "odc"
    CIERRE_ODC = "cierre_odc"
    CIERRE_CARTA = "cierre_carta"
    REPORTE_REALES = "reporte_reales"
    REPORTE_PROGRAMADOS = "reporte_programados"


# Prefijo propio por tipo (no se mezclan con `contratos/` ni entre sí).
_PREFIJOS: dict[TipoAdjuntoOrden, str] = {
    TipoAdjuntoOrden.ODC: "ordenes/odc/",
    TipoAdjuntoOrden.CIERRE_ODC: "ordenes/cierre/odc/",
    TipoAdjuntoOrden.CIERRE_CARTA: "ordenes/cierre/carta/",
    TipoAdjuntoOrden.REPORTE_REALES: "orden_estacion/reportes/reales/",
    TipoAdjuntoOrden.REPORTE_PROGRAMADOS: "orden_estacion/reportes/programados/",
}

router = build_adjuntos_router(
    tag="ordenes:adjuntos",
    tipos=TipoAdjuntoOrden,
    prefijos=_PREFIJOS,
    permiso_subir="ordenes:editar",
    permiso_descargar="ordenes:leer",
    content_disposition="inline",
    quitar_prefijo_uuid_en_descarga=True,
)
