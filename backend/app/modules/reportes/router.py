"""Router de F4 — Reportes. Solo lectura (sin `commit`, sin endpoint de escritura).

`estado-resultados` es `reportes_financiero` (Dirección); las 3 claves restantes
(`reportes_comercial`/`reportes_cobranza`/`reportes_operativo`) ya viven en la matriz
RBAC (`app/core/security.py`) desde esta tanda, aunque sus endpoints lleguen en
Tanda 2/3.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, requiere_permiso
from app.core.security_log import EventoSeguridad, registrar_evento_seguridad
from app.modules.reportes.repository import ReportesRepository
from app.modules.reportes.schemas import (
    DashboardCobranzaRead,
    DashboardComercialRead,
    DashboardOperativoRead,
    EstadoResultadosRead,
)
from app.modules.reportes.service import ReportesService
from app.shared.exportacion import construir_csv, construir_xlsx, neutralizar_formula

router = APIRouter(prefix="/reportes", tags=["reportes"])

_PATRON_PERIODO = r"^\d{4}-(0[1-9]|1[0-2])$"


def get_reportes_service(db: Session = Depends(get_db)) -> ReportesService:
    return ReportesService(ReportesRepository(db))


def _encabezados_y_filas(resultado: EstadoResultadosRead) -> tuple[list[str], list[list[object]]]:
    """Arma las filas planas (3 secciones + totales) que exportan ambos formatos, a
    partir del periodo ACTUAL ya calculado por el service — cero lógica de negocio
    aquí, solo aplanar lo que el service ya resolvió."""
    p = resultado.actual
    encabezados = ["Renglón", "Facturado en el periodo", "Pagado en el periodo"]
    filas: list[list[object]] = [
        ["INGRESOS", "", ""],
        ["Facturado", p.ingresos_facturado, ""],
        ["Cobrado", "", p.ingresos_cobrado],
        ["COSTOS DIRECTOS", "", ""],
        ["Pagos a afiliados", p.costos_afiliados.facturado, p.costos_afiliados.pagado],
        ["Pagos a agencias", p.costos_agencias.facturado, p.costos_agencias.pagado],
        [
            "Comisiones a vendedores",
            p.costos_comisiones_vendedores.facturado,
            p.costos_comisiones_vendedores.pagado,
        ],
    ]
    if p.costo_comisiones_agencias_pagado > 0:
        filas.append(["Comisiones a agencias", "", p.costo_comisiones_agencias_pagado])
    filas.extend(
        [
            ["COSTOS INDIRECTOS", "", ""],
            ["Nóminas", "", p.costo_nominas],
            ["Overhead", "", p.costo_overhead],
            ["Utilidad bruta", "", p.utilidad_bruta],
            ["Utilidad neta", "", p.utilidad_neta],
        ]
    )
    # Neutraliza cualquier celda de texto que pudiera empezar con un caracter
    # peligroso (ADR-025) — los encabezados de sección son literales fijos del código,
    # pero se pasa por el mismo mecanismo por defensa en profundidad.
    filas = [[neutralizar_formula(c) if isinstance(c, str) else c for c in fila] for fila in filas]
    return encabezados, filas


# Una "sección" exportable: (nombre, encabezados, filas). `Sequence`/`Any` para que el
# tipo calce exacto con `construir_xlsx` (dict es invariante en su valor; list no lo es).
Seccion = tuple[str, Sequence[str], Sequence[Sequence[Any]]]


def _hojas_y_csv_combinado(
    secciones: list[Seccion],
) -> tuple[dict[str, tuple[Sequence[str], Sequence[Sequence[Any]]]], list[str], list[list[object]]]:
    """De varias (nombre_sección, encabezados, filas) arma lo que necesitan los 2
    formatos: `hojas` para `.xlsx` (una hoja real por sección) y un único cuerpo
    combinado para `.csv` (que no tiene "hojas" — cada sección entra como un bloque
    con su propio título y encabezado, separado por una fila en blanco)."""
    hojas = {nombre: (enc, filas) for nombre, enc, filas in secciones}
    max_cols = max((len(enc) for _, enc, _ in secciones), default=1)
    filas_csv: list[list[object]] = []
    for nombre, enc, filas in secciones:
        fila_titulo: list[object] = [nombre, *([""] * (max_cols - 1))]
        fila_encabezado: list[object] = [*enc, *([""] * (max_cols - len(enc)))]
        filas_csv.append(fila_titulo)
        filas_csv.append(fila_encabezado)
        for fila in filas:
            fila_valores: list[object] = [*fila, *([""] * (max_cols - len(fila)))]
            filas_csv.append(fila_valores)
        filas_csv.append([""] * max_cols)
    return hojas, [""] * max_cols, filas_csv


def _responder_exportacion(
    hojas: dict[str, tuple[Sequence[str], Sequence[Sequence[Any]]]],
    encabezados_csv: list[str],
    filas_csv: list[list[object]],
    formato: str,
    nombre_archivo_base: str,
) -> Response:
    nombre_archivo = f"{nombre_archivo_base}.{formato}"
    if formato == "csv":
        contenido = construir_csv(encabezados_csv, filas_csv)
        media_type = "text/csv"
    else:
        contenido = construir_xlsx(hojas)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


def _secciones_comercial(d: DashboardComercialRead) -> list[Seccion]:
    return [
        (
            "Resumen",
            ["Indicador", "Valor"],
            [
                ["Ventas", d.ventas_total],
                ["Órdenes", d.ordenes_total],
                ["Ticket promedio", d.ticket_promedio if d.ticket_promedio is not None else ""],
                ["Comisiones vendedores", d.comisiones_vendedores_total],
                ["Anunciantes con ventas", d.anunciantes_con_ventas],
            ],
        ),
        (
            "Top vendedores",
            ["Vendedor", "Ventas", "Órdenes", "Comisión total"],
            [[v.nombre, v.ventas, v.ordenes, v.comision_total] for v in d.top_vendedores],
        ),
        (
            "Top anunciantes",
            ["Anunciante", "Ventas", "Órdenes"],
            [[a.nombre, a.ventas, a.ordenes] for a in d.top_anunciantes],
        ),
        (
            "Ventas por categoría",
            ["Categoría", "Ventas", "% del total"],
            [[c.nombre, c.ventas, c.pct if c.pct is not None else ""] for c in d.top_categorias],
        ),
        (
            "Ventas por agencia",
            ["Agencia", "Ventas", "% comisión", "Comisión"],
            [
                [
                    a.nombre,
                    a.ventas,
                    a.comision_pct if a.comision_pct is not None else "",
                    a.comision,
                ]
                for a in d.top_agencias
            ],
        ),
        (
            "Evolución mensual",
            ["Periodo", "Ventas"],
            [[e.periodo, e.ventas] for e in d.evolucion_mensual],
        ),
    ]


def _secciones_cobranza(d: DashboardCobranzaRead) -> list[Seccion]:
    return [
        (
            "Resumen",
            ["Indicador", "Valor"],
            [
                ["Total por cobrar", d.total_por_cobrar],
                ["Total vencido", d.total_vencido],
                ["Total de facturas", d.total_facturas],
                ["DSO promedio (días)", d.dso_promedio if d.dso_promedio is not None else ""],
                ["Cobrado del mes", d.cobrado_mes],
            ],
        ),
        (
            "Aging",
            ["Cubeta", "Importe", "Facturas"],
            [[a.bucket, a.importe, a.count] for a in d.aging],
        ),
        (
            "Cobranza por anunciante",
            ["Anunciante", "Por cobrar", "Vencido", "DSO (días)"],
            [
                [c.nombre, c.por_cobrar, c.vencido, c.dso if c.dso is not None else ""]
                for c in d.por_anunciante
            ],
        ),
        (
            "Evolución mensual",
            ["Periodo", "Facturado", "Cobrado"],
            [[e.periodo, e.facturado, e.cobrado] for e in d.evolucion_mensual],
        ),
    ]


def _secciones_operativo(d: DashboardOperativoRead) -> list[Seccion]:
    return [
        (
            "Resumen",
            ["Indicador", "Valor"],
            [
                [
                    "Cumplimiento general (%)",
                    d.cumplimiento_general_pct if d.cumplimiento_general_pct is not None else "",
                ],
                ["Spots ordenados", d.spots_ordenados_total],
                ["Spots transmitidos", d.spots_transmitidos_total],
                ["Incidencias totales", d.incidencias_total],
                ["Afiliados activos", d.afiliados_activos],
            ],
        ),
        (
            "Cumplimiento por estación",
            ["Estación", "Ordenado", "Ejecutado", "% Cumplimiento"],
            [
                [
                    e.nombre_estacion,
                    e.ordenado,
                    e.ejecutado,
                    e.pct_cumplimiento if e.pct_cumplimiento is not None else "",
                ]
                for e in d.cumplimiento_por_estacion
            ],
        ),
        (
            "Incidencias por afiliado",
            [
                "Afiliado",
                "Total",
                "Faltantes",
                "Excedentes",
                "Cambio horario",
                "Cambio fecha",
                "Spot no emitido",
                "OE totales",
                "Tasa (%)",
            ],
            [
                [
                    a.nombre_afiliado,
                    a.total,
                    a.faltantes,
                    a.excedentes,
                    a.cambios_horario,
                    a.cambios_fecha,
                    a.spots_no_emitidos,
                    a.oe_totales,
                    a.tasa_pct if a.tasa_pct is not None else "",
                ]
                for a in d.incidencias_por_afiliado
            ],
        ),
        (
            "Composición de incidencias",
            ["Tipo", "Total", "% del total"],
            [
                [t.tipo_incidencia, t.total, t.pct if t.pct is not None else ""]
                for t in d.composicion_incidencias
            ],
        ),
    ]


@router.get(
    "/estado-resultados",
    response_model=EstadoResultadosRead,
    dependencies=[Depends(requiere_permiso("reportes_financiero:leer"))],
)
def obtener_estado_resultados(
    periodo: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    svc: ReportesService = Depends(get_reportes_service),
) -> EstadoResultadosRead:
    return svc.estado_resultados(periodo)


@router.get(
    "/estado-resultados/exportar",
    dependencies=[Depends(requiere_permiso("reportes_financiero:leer"))],
)
def exportar_estado_resultados(
    periodo: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    usuario: CurrentUser = Depends(requiere_permiso("reportes_financiero:leer")),
    svc: ReportesService = Depends(get_reportes_service),
) -> Response:
    resultado = svc.estado_resultados(periodo)
    periodo_resuelto = resultado.actual.periodo
    encabezados, filas = _encabezados_y_filas(resultado)

    registrar_evento_seguridad(
        evento=EventoSeguridad.EXPORTACION_REPORTE,
        actor=usuario,
        objetivo="estado_resultados",
        detalle=f"periodo={periodo_resuelto} formato={formato}",
    )

    nombre_archivo = f"estado_resultados_{periodo_resuelto}.{formato}"
    if formato == "csv":
        contenido = construir_csv(encabezados, filas)
        media_type = "text/csv"
    else:
        contenido = construir_xlsx({"Estado de resultados": (encabezados, filas)})
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get(
    "/comercial",
    response_model=DashboardComercialRead,
    dependencies=[Depends(requiere_permiso("reportes_comercial:leer"))],
)
def obtener_dashboard_comercial(
    ventana: str = Query("mes", pattern="^(ytd|mes|trimestre)$"),
    periodo: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    svc: ReportesService = Depends(get_reportes_service),
) -> DashboardComercialRead:
    return svc.dashboard_comercial(ventana, periodo)


@router.get(
    "/comercial/exportar",
    dependencies=[Depends(requiere_permiso("reportes_comercial:leer"))],
)
def exportar_dashboard_comercial(
    ventana: str = Query("mes", pattern="^(ytd|mes|trimestre)$"),
    periodo: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    usuario: CurrentUser = Depends(requiere_permiso("reportes_comercial:leer")),
    svc: ReportesService = Depends(get_reportes_service),
) -> Response:
    resultado = svc.dashboard_comercial(ventana, periodo)
    hojas, encabezados_csv, filas_csv = _hojas_y_csv_combinado(_secciones_comercial(resultado))
    registrar_evento_seguridad(
        evento=EventoSeguridad.EXPORTACION_REPORTE,
        actor=usuario,
        objetivo="dashboard_comercial",
        detalle=f"ventana={ventana} periodo={resultado.periodo} formato={formato}",
    )
    return _responder_exportacion(
        hojas, encabezados_csv, filas_csv, formato, f"dashboard_comercial_{resultado.periodo}"
    )


@router.get(
    "/cobranza",
    response_model=DashboardCobranzaRead,
    dependencies=[Depends(requiere_permiso("reportes_cobranza:leer"))],
)
def obtener_dashboard_cobranza(
    mes: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    ventana_dso_dias: int = Query(90, ge=1, le=3650),
    svc: ReportesService = Depends(get_reportes_service),
) -> DashboardCobranzaRead:
    return svc.dashboard_cobranza(mes, ventana_dso_dias)


@router.get(
    "/cobranza/exportar",
    dependencies=[Depends(requiere_permiso("reportes_cobranza:leer"))],
)
def exportar_dashboard_cobranza(
    mes: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    ventana_dso_dias: int = Query(90, ge=1, le=3650),
    formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    usuario: CurrentUser = Depends(requiere_permiso("reportes_cobranza:leer")),
    svc: ReportesService = Depends(get_reportes_service),
) -> Response:
    resultado = svc.dashboard_cobranza(mes, ventana_dso_dias)
    hojas, encabezados_csv, filas_csv = _hojas_y_csv_combinado(_secciones_cobranza(resultado))
    registrar_evento_seguridad(
        evento=EventoSeguridad.EXPORTACION_REPORTE,
        actor=usuario,
        objetivo="dashboard_cobranza",
        detalle=f"mes={resultado.mes_cobrado} formato={formato}",
    )
    return _responder_exportacion(
        hojas, encabezados_csv, filas_csv, formato, f"dashboard_cobranza_{resultado.fecha_corte}"
    )


@router.get(
    "/operativo",
    response_model=DashboardOperativoRead,
    dependencies=[Depends(requiere_permiso("reportes_operativo:leer"))],
)
def obtener_dashboard_operativo(
    ventana: str = Query("mes", pattern="^(ytd|mes|trimestre)$"),
    periodo: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    svc: ReportesService = Depends(get_reportes_service),
) -> DashboardOperativoRead:
    return svc.dashboard_operativo(ventana, periodo)


@router.get(
    "/operativo/exportar",
    dependencies=[Depends(requiere_permiso("reportes_operativo:leer"))],
)
def exportar_dashboard_operativo(
    ventana: str = Query("mes", pattern="^(ytd|mes|trimestre)$"),
    periodo: str | None = Query(None, pattern=_PATRON_PERIODO, description="YYYY-MM"),
    formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    usuario: CurrentUser = Depends(requiere_permiso("reportes_operativo:leer")),
    svc: ReportesService = Depends(get_reportes_service),
) -> Response:
    resultado = svc.dashboard_operativo(ventana, periodo)
    hojas, encabezados_csv, filas_csv = _hojas_y_csv_combinado(_secciones_operativo(resultado))
    registrar_evento_seguridad(
        evento=EventoSeguridad.EXPORTACION_REPORTE,
        actor=usuario,
        objetivo="dashboard_operativo",
        detalle=f"ventana={ventana} periodo={resultado.periodo} formato={formato}",
    )
    return _responder_exportacion(
        hojas, encabezados_csv, filas_csv, formato, f"dashboard_operativo_{resultado.periodo}"
    )
