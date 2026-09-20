/** Requisiciones de pago (F3) — solicitudes de pago a afiliados, agencias y comisiones,
 * capturadas por CxP con autorización de Dirección/Admin por canal dedicado (ADR-046).
 *
 * "Comisiones" (tercer filtro de tipo) agrupa `comision_vendedor` + `comision_agencia`:
 * el backend solo filtra por UN `tipo_requisicion` a la vez, así que este pill trae el
 * lote sin filtrar y agrupa en el cliente — mismo criterio de "ampliar y filtrar en el
 * cliente" que el resto de este módulo.
 *
 * El "Origen del pago" del detalle (factura de afiliado/agencia u orden) se resuelve con
 * los combos de creación (facturas `autorizada`, órdenes de los últimos 100) — una
 * requisición cuyo origen ya no está en ese lote (p.ej. la factura pasó a `pagada` por
 * otra vía) muestra el folio crudo en vez del resuelto: limitación conocida, no rompe.
 */

import { useMemo, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, ConfirmDialog, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import type { FiltrosRequisicion } from "../../api";
import { badgeEstatusRequisicion, badgeTipoRequisicion, fmtFecha, fmtMoneda, fmtPorcentaje, oGuion } from "../../format";
import {
  useAgenciasInfo,
  useFacturasAfiliadoPagables,
  useFacturasAgenciaPagables,
  useOrdenesInfo,
  useRequisiciones,
  useVendedoresInfo,
} from "../../hooks";
import {
  ESTATUS_REQUISICION_LABEL,
  TIPO_REQUISICION_LABEL,
  type EstatusRequisicion,
  type Requisicion,
} from "../../types";
import { RequisicionForm } from "../components/RequisicionForm";

type FiltroEstatus = "all" | EstatusRequisicion;
type FiltroTipo = "all" | "pago_afiliado" | "pago_agencia" | "comisiones";

const FILTROS_ESTATUS = [
  { key: "all", label: "Todas" },
  { key: "pendiente", label: "Por autorizar" },
  { key: "autorizada", label: "Por pagar" },
  { key: "pagada", label: "Pagadas" },
  { key: "cancelada", label: "Canceladas" },
];

const FILTROS_TIPO = [
  { key: "all", label: "Todas" },
  { key: "pago_afiliado", label: "Afiliados" },
  { key: "pago_agencia", label: "Agencias" },
  { key: "comisiones", label: "Comisiones" },
];

interface Props {
  /** Preselecciona el filtro de estado — lo usan las "vistas operativas" del sidebar. */
  filtroInicial?: FiltroEstatus;
}

const mensajeDeError = (e: unknown): string =>
  e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

export function RequisicionesPage({ filtroInicial }: Props) {
  const [filtroEstatus, setFiltroEstatus] = useState<FiltroEstatus>(filtroInicial ?? "all");
  const [filtroTipo, setFiltroTipo] = useState<FiltroTipo>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Requisicion | null>(null);
  const [creando, setCreando] = useState(false);
  const [modo, setModo] = useState<"ver" | "pagar">("ver");
  const [fechaPago, setFechaPago] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [aCancelar, setACancelar] = useState<Requisicion | null>(null);

  const ampliando = filtroTipo === "comisiones";
  const filtros: FiltrosRequisicion = {
    page: ampliando ? 1 : page,
    size: ampliando ? 100 : size,
    q: q || undefined,
    estatus_requisicion: filtroEstatus === "all" ? undefined : filtroEstatus,
    tipo_requisicion: !ampliando && filtroTipo !== "all" ? filtroTipo : undefined,
  };

  const { list, crear, cambiarEstatus, autorizar } = useRequisiciones(filtros);
  const agencias = useAgenciasInfo();
  const vendedores = useVendedoresInfo();
  const facturasAfiliado = useFacturasAfiliadoPagables();
  const facturasAgencia = useFacturasAgenciaPagables();
  const ordenes = useOrdenesInfo();

  const agenciaMap = useMemo(() => new Map((agencias.data ?? []).map((a) => [a.agencia_id, a])), [agencias.data]);
  const vendedorMap = useMemo(() => new Map((vendedores.data ?? []).map((v) => [v.vendedor_id, v])), [vendedores.data]);
  const facturaAfiliadoMap = useMemo(
    () => new Map((facturasAfiliado.data ?? []).map((f) => [f.factura_afiliado_id, f])),
    [facturasAfiliado.data],
  );
  const facturaAgenciaMap = useMemo(
    () => new Map((facturasAgencia.data ?? []).map((f) => [f.factura_agencia_id, f])),
    [facturasAgencia.data],
  );
  const ordenMap = useMemo(() => new Map((ordenes.data ?? []).map((o) => [o.orden_id, o])), [ordenes.data]);

  let items = list.data?.items ?? [];
  if (ampliando) {
    items = items.filter((r) => r.tipo_requisicion === "comision_vendedor" || r.tipo_requisicion === "comision_agencia");
  }

  const beneficiario = (r: Requisicion): string => {
    if (r.tipo_requisicion === "pago_afiliado") return r.razon_social_afiliada ?? "—";
    if (r.tipo_requisicion === "pago_agencia" || r.tipo_requisicion === "comision_agencia") {
      return agenciaMap.get(r.agencia_id ?? "")?.nombre_agencia ?? "—";
    }
    return vendedorMap.get(r.vendedor_comision_id ?? "")?.nombre_vendedor ?? "—";
  };

  const origen = (r: Requisicion): string => {
    if (r.tipo_requisicion === "pago_afiliado") {
      return facturaAfiliadoMap.get(r.factura_afiliado_id ?? "")?.factura_emisora ?? "—";
    }
    if (r.tipo_requisicion === "pago_agencia") {
      return facturaAgenciaMap.get(r.factura_agencia_id ?? "")?.folio_factura_agencia ?? "—";
    }
    return ordenMap.get(r.orden_id ?? "")?.folio_orden ?? "—";
  };

  const seleccionar = (r: Requisicion) => {
    setSelected(r);
    setCreando(false);
    setModo("ver");
    setErrorAccion(null);
  };

  const ejecutar = async (accion: () => Promise<Requisicion>) => {
    setErrorAccion(null);
    try {
      setSelected(await accion());
      setModo("ver");
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onCrear = async (data: Parameters<typeof crear.mutateAsync>[0]) => {
    setSubmitError(null);
    try {
      setSelected(await crear.mutateAsync(data));
      setCreando(false);
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const confirmarCancelar = async () => {
    if (!aCancelar) return;
    setErrorAccion(null);
    try {
      const actualizada = await cambiarEstatus.mutateAsync({ id: aCancelar.requisicion_id, estatus: "cancelada" });
      setSelected(actualizada);
      setACancelar(null);
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
      setACancelar(null);
    }
  };

  const confirmarPago = async () => {
    if (!selected) return;
    await ejecutar(() =>
      cambiarEstatus.mutateAsync({
        id: selected.requisicion_id,
        estatus: "pagada",
        fecha_pago_requisicion: fechaPago || new Date().toISOString().slice(0, 10),
      }),
    );
  };

  let detail;
  if (creando) {
    detail = (
      <RequisicionForm
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={() => {
          setCreando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const esComision = selected.tipo_requisicion === "comision_vendedor" || selected.tipo_requisicion === "comision_agencia";
    const pct = selected.tipo_requisicion === "comision_vendedor" ? selected.porcentaje_comision_vendedor : selected.porcentaje_comision_agencia_req;
    const montoComision = selected.tipo_requisicion === "comision_vendedor" ? selected.requisicion_comision_vendedor : selected.requisicion_comision_agencia;

    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{selected.numero_requisicion}</div>
              <div className="dh-sub">
                <span className={`badge ${badgeEstatusRequisicion(selected.estatus_requisicion)}`}>
                  {ESTATUS_REQUISICION_LABEL[selected.estatus_requisicion]}
                </span>
                <span className={`badge ${badgeTipoRequisicion(selected.tipo_requisicion)}`}>
                  {TIPO_REQUISICION_LABEL[selected.tipo_requisicion]}
                </span>
                {selected.numero_oc_sap && (
                  <span className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>
                    {selected.numero_oc_sap}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="db">
          <div className="mc-row">
            <div className="mc">
              <div className="mc-lbl">Monto</div>
              <div className="mc-val">{fmtMoneda(selected.monto_requisicion)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">Estado</div>
              <div className="fv mono" style={{ marginBottom: 0, fontWeight: 600 }}>
                {ESTATUS_REQUISICION_LABEL[selected.estatus_requisicion]}
              </div>
            </div>
            <div className="mc">
              <div className="mc-lbl">Fecha pago</div>
              <div className="fv mono" style={{ marginBottom: 0, fontWeight: 600, color: selected.fecha_pago_requisicion ? "var(--green-text)" : undefined }}>
                {oGuion(selected.fecha_pago_requisicion)}
              </div>
            </div>
          </div>

          <div className="sec">Beneficiario</div>
          <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r)", padding: "11px 13px", marginBottom: 11 }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{beneficiario(selected)}</div>
          </div>

          <div className="sec">Origen del pago</div>
          <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r)", padding: "11px 13px" }}>
            <span className="mono" style={{ fontWeight: 600 }}>{origen(selected)}</span>
          </div>

          {esComision && (
            <>
              <div className="sec">Cálculo de comisión</div>
              <div className="r2">
                <div>
                  <div className="fl">% Comisión</div>
                  <div className="fv mono">{fmtPorcentaje(pct)}</div>
                </div>
                <div>
                  <div className="fl">
                    Monto <span className="fl-tag calc">Calc</span>
                  </div>
                  <div className="fv mono" style={{ fontWeight: 600 }}>
                    {fmtMoneda(montoComision)}
                  </div>
                </div>
              </div>
            </>
          )}

          {selected.tipo_requisicion === "pago_afiliado" && selected.diferencia_afiliada != null && (
            <>
              <div className="sec">Diferencia contra factura de afiliado</div>
              <div
                className="fv mono"
                style={{ fontWeight: 600, color: Number(selected.diferencia_afiliada) < 0 ? "var(--red-text)" : "var(--text)" }}
              >
                {fmtMoneda(selected.diferencia_afiliada)}
              </div>
            </>
          )}

          {selected.observaciones_cuentas_por_pagar && (
            <>
              <div className="sec">Observaciones CxP</div>
              <div className="fv muted">{selected.observaciones_cuentas_por_pagar}</div>
            </>
          )}

          {modo === "pagar" && (
            <>
              <div className="sec">Registrar pago</div>
              <div className="fl fl-required">Fecha de pago</div>
              <input
                type="date"
                className="fi"
                value={fechaPago}
                onChange={(e) => setFechaPago(e.target.value)}
              />
            </>
          )}

          {errorAccion && (
            <div className="state-msg error" style={{ textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
        </div>

        <div className="df">
          {modo === "pagar" ? (
            <>
              <button type="button" className="btn btn-sm" onClick={() => setModo("ver")} disabled={cambiarEstatus.isPending}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-sm btn-phase"
                onClick={() => void confirmarPago()}
                disabled={cambiarEstatus.isPending}
              >
                Confirmar pago
              </button>
            </>
          ) : (
            <>
              {selected.estatus_requisicion === "pendiente" && (
                <>
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => setACancelar(selected)}>
                    Cancelar
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-blue"
                    title="Solo Dirección o Admin pueden autorizar"
                    disabled={autorizar.isPending}
                    onClick={() => ejecutar(() => autorizar.mutateAsync(selected.requisicion_id))}
                  >
                    Autorizar →
                  </button>
                </>
              )}
              {selected.estatus_requisicion === "autorizada" && (
                <>
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => setACancelar(selected)}>
                    Cancelar
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-amber"
                    onClick={() => {
                      setFechaPago(new Date().toISOString().slice(0, 10));
                      setModo("pagar");
                    }}
                  >
                    Marcar pagada →
                  </button>
                </>
              )}
              {selected.estatus_requisicion === "pagada" && (
                <button type="button" className="btn btn-sm" disabled style={{ opacity: 0.6 }}>
                  ✓ Pagada el {fmtFecha(selected.fecha_pago_requisicion)}
                </button>
              )}
              {selected.estatus_requisicion === "cancelada" && (
                <button type="button" className="btn btn-sm" disabled style={{ opacity: 0.6 }}>
                  Cancelada
                </button>
              )}
            </>
          )}
        </div>
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona una requisición para ver el detalle." />;
  }

  const kpis = useMemo(() => {
    const todas = list.data?.items ?? [];
    const hoyMes = new Date().toISOString().slice(0, 7);
    return {
      porAutorizar: todas.filter((r) => r.estatus_requisicion === "pendiente").reduce((s, r) => s + Number(r.monto_requisicion), 0),
      porAutorizarCount: todas.filter((r) => r.estatus_requisicion === "pendiente").length,
      porPagar: todas.filter((r) => r.estatus_requisicion === "autorizada").reduce((s, r) => s + Number(r.monto_requisicion), 0),
      porPagarCount: todas.filter((r) => r.estatus_requisicion === "autorizada").length,
      pagadoMes: todas
        .filter((r) => r.estatus_requisicion === "pagada" && (r.fecha_pago_requisicion ?? "").slice(0, 7) === hoyMes)
        .reduce((s, r) => s + Number(r.monto_requisicion), 0),
    };
  }, [list.data]);

  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>No. req</th>
            <th>OC SAP</th>
            <th>Tipo</th>
            <th>Beneficiario</th>
            <th>Origen</th>
            <th className="td-right">Monto</th>
            <th>Pago</th>
            <th className="td-center">Estado</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr
              key={r.requisicion_id}
              className={selected?.requisicion_id === r.requisicion_id ? "sel" : ""}
              onClick={() => seleccionar(r)}
            >
              <td className="td-main mono">{r.numero_requisicion}</td>
              <td className="mono" style={{ fontSize: 11 }}>{oGuion(r.numero_oc_sap)}</td>
              <td>
                <span className={`badge ${badgeTipoRequisicion(r.tipo_requisicion)}`}>
                  {TIPO_REQUISICION_LABEL[r.tipo_requisicion]}
                </span>
              </td>
              <td className="td-main">{beneficiario(r)}</td>
              <td className="mono" style={{ fontSize: 11 }}>{origen(r)}</td>
              <td className="td-right mono">{fmtMoneda(r.monto_requisicion)}</td>
              <td className="mono" style={{ fontSize: 11, color: r.fecha_pago_requisicion ? "var(--green-text)" : "var(--text3)" }}>
                {oGuion(r.fecha_pago_requisicion)}
              </td>
              <td className="td-center">
                <span className={`badge ${badgeEstatusRequisicion(r.estatus_requisicion)}`}>
                  {ESTATUS_REQUISICION_LABEL[r.estatus_requisicion]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando requisiciones…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las requisiciones.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay requisiciones para el filtro seleccionado.</div>
      )}
      {!ampliando && list.data && list.data.total > 0 && (
        <Paginator
          page={page}
          size={size}
          total={list.data.total}
          onChange={(np, ns) => {
            setPage(np);
            setSize(ns);
          }}
        />
      )}
    </>
  );

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Requisiciones de pago</div>
          <div className="cat-sub">
            Solicitudes de pago a afiliados, agencias y comisiones. Cada requisición
            requiere autorización de Dirección antes de ejecutarse.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-phase"
          onClick={() => {
            setSelected(null);
            setCreando(true);
            setSubmitError(null);
          }}
        >
          <i className="pi pi-plus" aria-hidden="true" /> Nueva requisición
        </button>
      </div>

      <div className="kpi-strip">
        <div className="kpi-box warn">
          <div className="kpi-lbl" style={{ color: "var(--amber-text)" }}>Por autorizar</div>
          <div className="kpi-val" style={{ color: "var(--amber-text)" }}>{fmtMoneda(String(kpis.porAutorizar))}</div>
          <div className="kpi-sub">{kpis.porAutorizarCount} requisiciones</div>
        </div>
        <div className="kpi-box">
          <div className="kpi-lbl">Autorizadas (por pagar)</div>
          <div className="kpi-val">{fmtMoneda(String(kpis.porPagar))}</div>
          <div className="kpi-sub">{kpis.porPagarCount} requisiciones</div>
        </div>
        <div className="kpi-box success">
          <div className="kpi-lbl" style={{ color: "var(--green-text)" }}>Pagado este mes</div>
          <div className="kpi-val" style={{ color: "var(--green-text)" }}>{fmtMoneda(String(kpis.pagadoMes))}</div>
        </div>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar número o OC SAP…"
        filterLabel="Estado"
        filters={FILTROS_ESTATUS}
        activeFilter={filtroEstatus}
        onFilter={(k) => {
          setFiltroEstatus(k as FiltroEstatus);
          setPage(1);
        }}
        filterLabel2="Tipo"
        filters2={FILTROS_TIPO}
        activeFilter2={filtroTipo}
        onFilter2={(k) => {
          setFiltroTipo(k as FiltroTipo);
          setPage(1);
        }}
        count={`${items.length}${ampliando ? "" : ` de ${list.data?.total ?? 0}`}`}
      />

      <ListDetailLayout list={listNode} detail={detail} />

      <ConfirmDialog
        visible={!!aCancelar}
        title="Cancelar requisición"
        message={aCancelar ? `¿Cancelar la requisición ${aCancelar.numero_requisicion}?` : ""}
        confirmLabel="Cancelar requisición"
        danger
        loading={cambiarEstatus.isPending}
        onConfirm={() => void confirmarCancelar()}
        onCancel={() => setACancelar(null)}
      />
    </>
  );
}
