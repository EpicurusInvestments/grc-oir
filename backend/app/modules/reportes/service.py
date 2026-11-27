"""Servicio de F4-01 (Estado de resultados): arma las ventanas de fecha, llama al
repositorio y aplica las fórmulas (prorrateo a sin-IVA, utilidad bruta/neta, márgenes,
tendencia). El repositorio SOLO agrega en SQL; toda la aritmética de dinero (que debe
corroborarse contra SQL Server real, ADR-039) vive aquí.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.core.errors import DomainError
from app.modules.facturacion.costo_adicional import TipoCosto
from app.modules.ordenes.incidencia import TipoIncidencia
from app.modules.reportes.repository import FilaProrrateable, ReportesRepository
from app.modules.reportes.schemas import (
    AgingCubeta,
    CobradoFacturadoMensual,
    CobranzaPorAnunciante,
    CumplimientoEstacion,
    DashboardCobranzaRead,
    DashboardComercialRead,
    DashboardOperativoRead,
    EstadoResultadosPeriodo,
    EstadoResultadosRead,
    IncidenciasPorAfiliado,
    IncidenciasPorTipo,
    RenglonFacturadoPagado,
    TendenciaPct,
    VentaMensual,
    VentasPorAgencia,
    VentasPorAnunciante,
    VentasPorCategoria,
    VentasPorVendedor,
)

_VENTANAS_COMERCIAL = ("ytd", "mes", "trimestre")
_AGING_BUCKETS = ("corriente", "1-30", "31-60", "61-90", "90+")

logger = logging.getLogger("grcoir.reportes")

_PATRON_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# ADR-261: "hoy" para el default de "mes en curso" se calcula en hora de México, nunca
# UTC — entre las 18:00 y medianoche, UTC ya es el día/mes siguiente.
_ZONA_MX = ZoneInfo("America/Mexico_City")
_MESES_HISTORICO = 6
_DOS_DECIMALES = Decimal("0.01")


@dataclass(frozen=True)
class _Ventana:
    periodo: str  # "YYYY-MM"
    inicio: date
    fin_exclusivo: date
    en_curso: bool


def _validar_periodo(periodo: str) -> None:
    if not _PATRON_PERIODO.match(periodo):
        raise DomainError(
            f"'{periodo}' no es un periodo válido. Formato esperado: YYYY-MM (mes 01-12)."
        )


def _mes_en_curso() -> str:
    hoy = datetime.now(_ZONA_MX).date()
    return f"{hoy.year:04d}-{hoy.month:02d}"


def _sumar_meses(anio: int, mes: int, delta: int) -> tuple[int, int]:
    indice = (anio * 12 + (mes - 1)) + delta
    return indice // 12, indice % 12 + 1


def _ventana_de(periodo: str, periodo_actual: str) -> _Ventana:
    anio, mes = (int(x) for x in periodo.split("-"))
    anio_fin, mes_fin = _sumar_meses(anio, mes, 1)
    return _Ventana(
        periodo=periodo,
        inicio=date(anio, mes, 1),
        fin_exclusivo=date(anio_fin, mes_fin, 1),
        en_curso=periodo == periodo_actual,
    )


def _ventanas_historico(periodo: str) -> list[_Ventana]:
    """Las `_MESES_HISTORICO` ventanas terminando en `periodo` (inclusive), orden
    cronológico ascendente."""
    anio, mes = (int(x) for x in periodo.split("-"))
    periodo_actual = _mes_en_curso()
    ventanas = []
    for delta in range(-(_MESES_HISTORICO - 1), 1):
        a, m = _sumar_meses(anio, mes, delta)
        ventanas.append(_ventana_de(f"{a:04d}-{m:02d}", periodo_actual))
    return ventanas


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)


def _prorratear_y_sumar(filas: list[FilaProrrateable], etiqueta: str) -> Decimal:
    """`SUM(ROUND(monto * sin_iva / con_iva, 2))` — redondeado FILA POR FILA antes de
    sumar (para que la consulta SQL de validación pueda reproducir el mismo número
    exacto). Si `con_iva = 0` para alguna fila (no debería pasar — el CHECK de la
    factura exige `>= 0` y una factura en 0 no tiene sentido de negocio, pero el código
    no lo prohíbe), se trata como razón 0 y se reporta al log — nunca truena."""
    total = Decimal("0")
    for fila in filas:
        if fila.con_iva == 0:
            logger.warning(
                "reportes.prorrateo_division_cero etiqueta=%s monto=%s", etiqueta, fila.monto
            )
            continue
        razon = fila.sin_iva / fila.con_iva
        total += _redondear(fila.monto * razon)
    return total


def _pct(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    if denominador == 0:
        return None
    return _redondear(numerador / denominador * 100)


def _pct_cambio(actual: Decimal, anterior: Decimal) -> Decimal | None:
    if anterior == 0:
        return None
    return _redondear((actual - anterior) / abs(anterior) * 100)


def _ventana_comercial(ventana: str, periodo: str) -> tuple[date, date]:
    if ventana not in _VENTANAS_COMERCIAL:
        raise DomainError(
            f"'{ventana}' no es una ventana válida. Usa: {', '.join(_VENTANAS_COMERCIAL)}."
        )
    anio, mes = (int(x) for x in periodo.split("-"))
    if ventana == "mes":
        inicio = date(anio, mes, 1)
        a_fin, m_fin = _sumar_meses(anio, mes, 1)
    elif ventana == "trimestre":
        mes_inicio_trimestre = ((mes - 1) // 3) * 3 + 1
        inicio = date(anio, mes_inicio_trimestre, 1)
        a_fin, m_fin = _sumar_meses(anio, mes_inicio_trimestre, 3)
    else:  # ytd
        inicio = date(anio, 1, 1)
        a_fin, m_fin = _sumar_meses(anio, mes, 1)
    return inicio, date(a_fin, m_fin, 1)


class ReportesService:
    def __init__(self, repo: ReportesRepository) -> None:
        self._repo = repo

    def _calcular_periodo(self, ventana: _Ventana) -> EstadoResultadosPeriodo:
        repo = self._repo
        inicio, fin = ventana.inicio, ventana.fin_exclusivo

        ingresos_facturado = repo.facturado_clientes(inicio, fin)
        ingresos_cobrado = _prorratear_y_sumar(repo.filas_cobrado(inicio, fin), "cobrado")

        pagado_afiliados = _prorratear_y_sumar(
            repo.filas_pagado_afiliados(inicio, fin), "pagado_afiliados"
        )
        pagado_agencias = _prorratear_y_sumar(
            repo.filas_pagado_agencias(inicio, fin), "pagado_agencias"
        )
        pagado_comisiones_vendedores = _prorratear_y_sumar(
            repo.filas_pagado_comisiones_vendedores(inicio, fin), "pagado_comisiones_vendedores"
        )
        pagado_comisiones_agencias = _prorratear_y_sumar(
            repo.filas_pagado_comisiones_agencias(inicio, fin), "pagado_comisiones_agencias"
        )

        costo_nominas = repo.costo_por_tipo(ventana.periodo, TipoCosto.NOMINA)
        costo_overhead = repo.costo_por_tipo(ventana.periodo, TipoCosto.OVERHEAD)

        utilidad_bruta = ingresos_cobrado - (
            pagado_afiliados
            + pagado_agencias
            + pagado_comisiones_vendedores
            + pagado_comisiones_agencias
        )
        utilidad_neta = utilidad_bruta - costo_nominas - costo_overhead

        return EstadoResultadosPeriodo(
            periodo=ventana.periodo,
            en_curso=ventana.en_curso,
            ingresos_facturado=ingresos_facturado,
            ingresos_cobrado=ingresos_cobrado,
            costos_afiliados=RenglonFacturadoPagado(
                facturado=repo.facturado_afiliados(inicio, fin), pagado=pagado_afiliados
            ),
            costos_agencias=RenglonFacturadoPagado(
                facturado=repo.facturado_agencias(inicio, fin), pagado=pagado_agencias
            ),
            costos_comisiones_vendedores=RenglonFacturadoPagado(
                facturado=repo.facturado_vendedores(inicio, fin),
                pagado=pagado_comisiones_vendedores,
            ),
            costo_comisiones_agencias_pagado=pagado_comisiones_agencias,
            costo_nominas=costo_nominas,
            costo_overhead=costo_overhead,
            utilidad_bruta=utilidad_bruta,
            utilidad_neta=utilidad_neta,
            margen_bruto_pct=_pct(utilidad_bruta, ingresos_cobrado),
            margen_neto_pct=_pct(utilidad_neta, ingresos_cobrado),
            pct_cobranza=_pct(ingresos_cobrado, ingresos_facturado),
            costo_afiliados_pct_cobrado=_pct(pagado_afiliados, ingresos_cobrado),
        )

    def estado_resultados(self, periodo: str | None) -> EstadoResultadosRead:
        periodo = periodo or _mes_en_curso()
        _validar_periodo(periodo)

        ventanas = _ventanas_historico(periodo)
        historico = [self._calcular_periodo(v) for v in ventanas]
        actual = historico[-1]
        anterior = historico[-2]

        tendencia = TendenciaPct(
            ingresos_cobrado_pct=_pct_cambio(actual.ingresos_cobrado, anterior.ingresos_cobrado),
            utilidad_bruta_pct=_pct_cambio(actual.utilidad_bruta, anterior.utilidad_bruta),
            utilidad_neta_pct=_pct_cambio(actual.utilidad_neta, anterior.utilidad_neta),
        )

        return EstadoResultadosRead(
            actual=actual, anterior=anterior, tendencia=tendencia, historico=historico
        )

    # ── Dashboard comercial (F4-02) ───────────────────────────────────────────────
    def dashboard_comercial(self, ventana: str, periodo: str | None) -> DashboardComercialRead:
        periodo = periodo or _mes_en_curso()
        _validar_periodo(periodo)
        inicio, fin = _ventana_comercial(ventana, periodo)
        repo = self._repo

        ventas_total, ordenes_total = repo.ventas_totales(inicio, fin)
        ticket_promedio = _redondear(ventas_total / ordenes_total) if ordenes_total else None
        anunciantes_con_ventas = repo.anunciantes_con_ventas(inicio, fin)

        # Vendedores: "Ventas" SOLO como principal (nunca se duplica la orden); la
        # comisión suma ambos roles (principal + secundario), por vendedor.
        acumulador: dict[uuid.UUID, dict[str, Decimal | int]] = {}
        for fila in repo.filas_ventas_principal(inicio, fin):
            d = acumulador.setdefault(
                fila.vendedor_id, {"ventas": Decimal("0"), "ordenes": 0, "comision": Decimal("0")}
            )
            d["ventas"] = d["ventas"] + fila.total
            d["ordenes"] = int(d["ordenes"]) + 1
            d["comision"] = d["comision"] + _redondear(
                fila.total * (fila.porcentaje or Decimal("0")) / 100
            )
        for fila in repo.filas_comision_secundario(inicio, fin):
            d = acumulador.setdefault(
                fila.vendedor_id, {"ventas": Decimal("0"), "ordenes": 0, "comision": Decimal("0")}
            )
            d["comision"] = d["comision"] + _redondear(
                fila.total * (fila.porcentaje or Decimal("0")) / 100
            )
        comisiones_vendedores_total = sum(
            (Decimal(d["comision"]) for d in acumulador.values()), Decimal("0")
        )
        nombres_v = repo.nombres_vendedores(set(acumulador.keys()))
        top_vendedores = sorted(
            (
                VentasPorVendedor(
                    vendedor_id=vid,
                    nombre=nombres_v.get(vid, "—"),
                    ventas=Decimal(d["ventas"]),
                    ordenes=int(d["ordenes"]),
                    comision_total=Decimal(d["comision"]),
                )
                for vid, d in acumulador.items()
            ),
            key=lambda x: x.ventas,
            reverse=True,
        )[:10]

        # Anunciantes
        filas_anunciante = repo.ventas_por_anunciante(inicio, fin)
        nombres_a = repo.nombres_anunciantes({a for a, _, _ in filas_anunciante})
        top_anunciantes = [
            VentasPorAnunciante(
                anunciante_id=aid, nombre=nombres_a.get(aid, "—"), ventas=v, ordenes=o
            )
            for aid, v, o in filas_anunciante[:10]
        ]

        # Categorías (Giro Empresarial)
        filas_cat = repo.ventas_por_categoria(inicio, fin)
        nombres_cat = repo.nombres_categorias({c for c, _ in filas_cat if c is not None})
        top_categorias = [
            VentasPorCategoria(
                categoria_id=cid,
                nombre=nombres_cat.get(cid, "—") if cid is not None else "Sin categoría",
                ventas=v,
                pct=_pct(v, ventas_total),
            )
            for cid, v in filas_cat[:10]
        ]

        # Agencias (incluye "Trato directo" = agencia_id NULL); % promedio ponderado
        # calculado en Python sobre la comisión real, no un promedio simple de %.
        acumulador_ag: dict[uuid.UUID | None, dict[str, Decimal]] = {}
        for agencia_id, total, pct in repo.filas_ventas_agencia(inicio, fin):
            dag = acumulador_ag.setdefault(
                agencia_id, {"ventas": Decimal("0"), "comision": Decimal("0")}
            )
            dag["ventas"] += total
            if agencia_id is not None:
                dag["comision"] += _redondear(total * (pct or Decimal("0")) / 100)
        nombres_ag = repo.nombres_agencias({a for a in acumulador_ag if a is not None})
        top_agencias = sorted(
            (
                VentasPorAgencia(
                    agencia_id=aid,
                    nombre=nombres_ag.get(aid, "—") if aid is not None else "Trato directo",
                    ventas=d["ventas"],
                    comision_pct=_pct(d["comision"], d["ventas"]) if aid is not None else None,
                    comision=d["comision"],
                )
                for aid, d in acumulador_ag.items()
            ),
            key=lambda x: x.ventas,
            reverse=True,
        )[:10]

        # Evolución mensual: 6 meses terminando en el mes de `periodo` (no en la
        # ventana elegida — da contexto histórico siempre al mismo tamaño).
        anio_p, mes_p = (int(x) for x in periodo.split("-"))
        evolucion = []
        for delta in range(-(_MESES_HISTORICO - 1), 1):
            a, m = _sumar_meses(anio_p, mes_p, delta)
            a_fin, m_fin = _sumar_meses(a, m, 1)
            ventas_mes = repo.ventas_por_mes(date(a, m, 1), date(a_fin, m_fin, 1))
            evolucion.append(VentaMensual(periodo=f"{a:04d}-{m:02d}", ventas=ventas_mes))

        return DashboardComercialRead(
            ventana=ventana,
            periodo=periodo,
            desde=inicio.isoformat(),
            hasta=fin.isoformat(),
            ventas_total=ventas_total,
            ordenes_total=ordenes_total,
            ticket_promedio=ticket_promedio,
            comisiones_vendedores_total=comisiones_vendedores_total,
            anunciantes_con_ventas=anunciantes_con_ventas,
            top_vendedores=top_vendedores,
            top_anunciantes=top_anunciantes,
            top_categorias=top_categorias,
            top_agencias=top_agencias,
            evolucion_mensual=evolucion,
        )

    # ── Dashboard de cobranza (F4-03) ─────────────────────────────────────────────
    def dashboard_cobranza(
        self, mes: str | None, ventana_dso_dias: int = 90
    ) -> DashboardCobranzaRead:
        mes = mes or _mes_en_curso()
        _validar_periodo(mes)
        if ventana_dso_dias <= 0:
            raise DomainError("'ventana_dso_dias' debe ser mayor a 0.")
        repo = self._repo
        hoy = datetime.now(_ZONA_MX).date()

        filas = repo.filas_cobranza_abierta()
        total_por_cobrar = sum((f.saldo for f in filas), Decimal("0"))
        total_vencido = sum(
            (f.saldo for f in filas if f.fecha_estimada_cobro < hoy), Decimal("0")
        )

        cubetas: dict[str, list[Decimal | int]] = {b: [Decimal("0"), 0] for b in _AGING_BUCKETS}
        por_anunciante_saldo: dict[uuid.UUID, Decimal] = {}
        por_anunciante_vencido: dict[uuid.UUID, Decimal] = {}
        for f in filas:
            dias = (hoy - f.fecha_estimada_cobro).days
            if dias <= 0:
                clave = "corriente"
            elif dias <= 30:
                clave = "1-30"
            elif dias <= 60:
                clave = "31-60"
            elif dias <= 90:
                clave = "61-90"
            else:
                clave = "90+"
            cubetas[clave][0] = Decimal(cubetas[clave][0]) + f.saldo
            cubetas[clave][1] = int(cubetas[clave][1]) + 1
            por_anunciante_saldo[f.anunciante_id] = (
                por_anunciante_saldo.get(f.anunciante_id, Decimal("0")) + f.saldo
            )
            if dias > 0:
                por_anunciante_vencido[f.anunciante_id] = (
                    por_anunciante_vencido.get(f.anunciante_id, Decimal("0")) + f.saldo
                )
        aging = [
            AgingCubeta(bucket=b, importe=Decimal(v[0]), count=int(v[1]))
            for b, v in cubetas.items()
        ]

        inicio_dso = hoy - timedelta(days=ventana_dso_dias)
        ventas_ventana = repo.facturado_con_iva(inicio_dso, hoy + timedelta(days=1))
        dso_promedio = (
            _redondear(total_por_cobrar / ventas_ventana * ventana_dso_dias)
            if ventas_ventana > 0
            else None
        )

        ventas_por_anunciante_dso = repo.facturado_con_iva_por_anunciante(
            inicio_dso, hoy + timedelta(days=1)
        )
        nombres_a = repo.nombres_anunciantes(set(por_anunciante_saldo.keys()))
        por_anunciante = sorted(
            (
                CobranzaPorAnunciante(
                    anunciante_id=aid,
                    nombre=nombres_a.get(aid, "—"),
                    por_cobrar=saldo,
                    vencido=por_anunciante_vencido.get(aid, Decimal("0")),
                    dso=(
                        _redondear(
                            saldo / ventas_por_anunciante_dso[aid] * ventana_dso_dias
                        )
                        if ventas_por_anunciante_dso.get(aid)
                        else None
                    ),
                )
                for aid, saldo in por_anunciante_saldo.items()
            ),
            key=lambda x: x.por_cobrar,
            reverse=True,
        )

        anio_m, mes_m = (int(x) for x in mes.split("-"))
        a_fin, m_fin = _sumar_meses(anio_m, mes_m, 1)
        cobrado_mes = repo.cobrado_en_mes(date(anio_m, mes_m, 1), date(a_fin, m_fin, 1))

        evolucion = []
        for delta in range(-(_MESES_HISTORICO - 1), 1):
            a, m = _sumar_meses(anio_m, mes_m, delta)
            a2, m2 = _sumar_meses(a, m, 1)
            inicio_m, fin_m = date(a, m, 1), date(a2, m2, 1)
            evolucion.append(
                CobradoFacturadoMensual(
                    periodo=f"{a:04d}-{m:02d}",
                    facturado=repo.facturado_con_iva(inicio_m, fin_m),
                    cobrado=repo.cobrado_en_mes(inicio_m, fin_m),
                )
            )

        return DashboardCobranzaRead(
            fecha_corte=hoy.isoformat(),
            mes_cobrado=mes,
            ventana_dso_dias=ventana_dso_dias,
            total_por_cobrar=total_por_cobrar,
            total_vencido=total_vencido,
            total_facturas=len(filas),
            dso_promedio=dso_promedio,
            cobrado_mes=cobrado_mes,
            aging=aging,
            por_anunciante=por_anunciante,
            evolucion_mensual=evolucion,
        )

    # ── Dashboard operativo (F4-04) ───────────────────────────────────────────────
    def dashboard_operativo(self, ventana: str, periodo: str | None) -> DashboardOperativoRead:
        periodo = periodo or _mes_en_curso()
        _validar_periodo(periodo)
        inicio, fin = _ventana_comercial(ventana, periodo)
        repo = self._repo

        filas_cumpl = repo.cumplimiento_por_estacion(inicio, fin)
        spots_ordenados_total = sum(f.ordenado for f in filas_cumpl)
        spots_transmitidos_total = sum(f.ejecutado for f in filas_cumpl)
        cumplimiento_general_pct = _pct(
            Decimal(spots_transmitidos_total), Decimal(spots_ordenados_total)
        )
        cumplimiento_por_estacion = sorted(
            (
                CumplimientoEstacion(
                    estacion_id=f.estacion_id,
                    nombre_estacion=f.nombre_estacion,
                    ordenado=f.ordenado,
                    ejecutado=f.ejecutado,
                    pct_cumplimiento=_pct(Decimal(f.ejecutado), Decimal(f.ordenado)),
                )
                for f in filas_cumpl
                if f.ordenado > 0  # división por cero: se excluye del ranking, no truena
            ),
            key=lambda x: x.ordenado,
            reverse=True,
        )

        oe_por_afiliado = repo.oe_verificadas_por_afiliado(inicio, fin)
        afiliados_activos = len(oe_por_afiliado)

        acumulador: dict[uuid.UUID, dict[str, Any]] = {}
        for fila in repo.incidencias_por_afiliado_y_tipo(inicio, fin):
            d = acumulador.setdefault(
                fila.afiliado_id,
                {
                    "nombre": fila.nombre_afiliado,
                    "total": 0,
                    TipoIncidencia.FALTANTE.value: 0,
                    TipoIncidencia.EXCEDENTE.value: 0,
                    TipoIncidencia.CAMBIO_HORARIO.value: 0,
                    TipoIncidencia.CAMBIO_FECHA.value: 0,
                    TipoIncidencia.SPOT_NO_EMITIDO.value: 0,
                },
            )
            d["total"] = int(d["total"]) + fila.total
            d[fila.tipo_incidencia] = int(d[fila.tipo_incidencia]) + fila.total

        def _fila_afiliado(aid: uuid.UUID, d: dict[str, Any]) -> IncidenciasPorAfiliado:
            oe_totales = oe_por_afiliado.get(aid, 0)
            tasa = _pct(Decimal(int(d["total"])), Decimal(oe_totales))
            return IncidenciasPorAfiliado(
                afiliado_id=aid,
                nombre_afiliado=str(d["nombre"]),
                total=int(d["total"]),
                faltantes=int(d[TipoIncidencia.FALTANTE.value]),
                excedentes=int(d[TipoIncidencia.EXCEDENTE.value]),
                cambios_horario=int(d[TipoIncidencia.CAMBIO_HORARIO.value]),
                cambios_fecha=int(d[TipoIncidencia.CAMBIO_FECHA.value]),
                spots_no_emitidos=int(d[TipoIncidencia.SPOT_NO_EMITIDO.value]),
                oe_totales=oe_totales,
                tasa_pct=tasa,
                alerta=tasa is not None and tasa > 10,
            )

        incidencias_por_afiliado = sorted(
            (_fila_afiliado(aid, d) for aid, d in acumulador.items()),
            key=lambda x: x.total,
            reverse=True,
        )

        composicion_raw = repo.composicion_incidencias(inicio, fin)
        incidencias_total = sum(composicion_raw.values())
        composicion_incidencias = [
            IncidenciasPorTipo(
                tipo_incidencia=t.value,
                total=composicion_raw.get(t.value, 0),
                pct=_pct(Decimal(composicion_raw.get(t.value, 0)), Decimal(incidencias_total)),
            )
            for t in TipoIncidencia
        ]

        return DashboardOperativoRead(
            ventana=ventana,
            periodo=periodo,
            desde=inicio.isoformat(),
            hasta=fin.isoformat(),
            cumplimiento_general_pct=cumplimiento_general_pct,
            spots_ordenados_total=spots_ordenados_total,
            spots_transmitidos_total=spots_transmitidos_total,
            incidencias_total=incidencias_total,
            afiliados_activos=afiliados_activos,
            cumplimiento_por_estacion=cumplimiento_por_estacion,
            incidencias_por_afiliado=incidencias_por_afiliado,
            composicion_incidencias=composicion_incidencias,
        )
