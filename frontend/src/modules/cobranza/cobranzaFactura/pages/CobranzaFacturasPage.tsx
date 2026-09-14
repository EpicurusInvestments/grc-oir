/** Cobranza de facturas (F3) — seguimiento del cobro de cada `FacturaCliente` timbrada.
 *
 * `CobranzaFactura` no tiene alta propia (la crea el handoff de F2 al timbrar, ADR-072):
 * esta pantalla es puramente de seguimiento y captura de pagos, nunca de creación.
 *
 * Búsqueda y la vista "Vencidas": el backend NO indexa texto libre sobre esta lista
 * (`CobranzaFacturaRepository._apply_filters` solo filtra por `factura_id`/`anunciante_id`/
 * `estatus_cobro`, no por `q`) ni conoce el badge `vencida` (es derivado, no una columna
 * consultable). Así que, mientras se busca o se activa "Vencidas", esta pantalla trae
 * hasta 100 filas y filtra en el cliente — limitación conocida de esta primera tanda, no
 * bloqueante (un catálogo de cobranzas mucho más grande pediría un filtro real del lado
 * del backend).
 */

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, ConfirmDialog, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import type { FiltrosCobranzaFactura } from "../../api";
import { BADGE_VENCIDA, badgeEstatusCobro, diasHasta, fmtFecha, fmtMoneda, oGuion } from "../../format";
import {
  useAnunciantesInfo,
  useCobranzaFactura,
  useCobranzaFacturaPorFacturaId,
  useCobranzaFacturas,
  useFacturaClienteResumen,
  useMetodosDePago,
  usePagosCliente,
} from "../../hooks";
import { ESTATUS_COBRO_LABEL, type CobranzaFactura, type PagoCliente, type PagoClienteCreate } from "../../types";
import { RegistrarPagoForm } from "../components/RegistrarPagoForm";

type Filtro = "all" | "pendiente" | "cobro_parcial" | "cobrada" | "vencidas";

const FILTROS = [
  { key: "all", label: "Todas" },
  { key: "vencidas", label: "Vencidas" },
  { key: "pendiente", label: "Pendientes" },
  { key: "cobro_parcial", label: "Parciales" },
  { key: "cobrada", label: "Cobradas" },
];

interface Props {
  /** Preselecciona un filtro al entrar — lo usan las "vistas operativas" del sidebar. */
  filtroInicial?: Filtro;
}

const mensajeDeError = (e: unknown): string =>
  e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

export function CobranzaFacturasPage({ filtroInicial }: Props) {
  const [searchParams] = useSearchParams();
  const [filtro, setFiltro] = useState<Filtro>(filtroInicial ?? "all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modo, setModo] = useState<"ver" | "pagar" | "editar">("ver");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [pagoAEliminar, setPagoAEliminar] = useState<PagoCliente | null>(null);

  // El backend no soporta `q` ni "vencida" en el filtro: se amplía a un lote de 100 y se
  // filtra en el cliente (ver docstring del módulo).
  const ampliando = q.trim() !== "" || filtro === "vencidas";
  const filtros: FiltrosCobranzaFactura = ampliando
    ? { page: 1, size: 100 }
    : { page, size, estatus_cobro: filtro === "all" ? undefined : filtro };

  const { list, actualizar } = useCobranzaFacturas(filtros);
  const anunciantes = useAnunciantesInfo();
  const anuncianteMap = useMemo(
    () => new Map((anunciantes.data ?? []).map((a) => [a.anunciante_id, a])),
    [anunciantes.data],
  );

  // KPIs de la franja superior: se calculan sobre un lote amplio, INDEPENDIENTE del
  // filtro/paginación activos en la lista (mismo límite de 100 que el resto del módulo).
  const { list: paraKpis } = useCobranzaFacturas({ page: 1, size: 100 });
  const kpis = useMemo(() => {
    const todas = paraKpis.data?.items ?? [];
    const hoyMes = new Date().toISOString().slice(0, 7);
    const porCobrar = todas
      .filter((c) => c.estatus_cobro !== "cobrada")
      .reduce((s, c) => s + Number(c.importe_pendiente_cobro), 0);
    const vencido = todas
      .filter((c) => c.vencida)
      .reduce((s, c) => s + Number(c.importe_pendiente_cobro), 0);
    const porVencer7d = todas
      .filter((c) => c.estatus_cobro !== "cobrada" && !c.vencida)
      .filter((c) => {
        const d = diasHasta(c.fecha_estimada_cobro);
        return d >= 0 && d <= 7;
      })
      .reduce((s, c) => s + Number(c.importe_pendiente_cobro), 0);
    const cobradasMes = todas.filter(
      (c) => c.estatus_cobro === "cobrada" && (c.fecha_cobro ?? "").slice(0, 7) === hoyMes,
    );
    const cobradoMes = cobradasMes.reduce(
      (s, c) => s + Number(c.importe_cobrado) + Number(c.importe_pendiente_cobro),
      0,
    );
    return {
      porCobrar,
      vencido,
      vencidasCount: todas.filter((c) => c.vencida).length,
      porVencer7d,
      cobradoMes,
      cobradasMesCount: cobradasMes.length,
      totalNoCobradas: todas.filter((c) => c.estatus_cobro !== "cobrada").length,
    };
  }, [paraKpis.data]);

  let items = list.data?.items ?? [];
  if (ampliando) {
    if (filtro === "vencidas") items = items.filter((c) => c.vencida);
    const qq = q.trim().toLowerCase();
    if (qq) {
      items = items.filter((c) => {
        const an = anuncianteMap.get(c.anunciante_id);
        return (
          (c.numero_factura ?? "").toLowerCase().includes(qq) ||
          (an?.nombre_comercial ?? "").toLowerCase().includes(qq)
        );
      });
    }
  }

  // Deep-link desde F2 ("Pasa a CxC" en FacturasClientePage): ?factura_id=... preselecciona
  // la cobranza correspondiente sin importar en qué página/filtro esté.
  const facturaIdParam = searchParams.get("factura_id");

  const detail = useCobranzaFactura(selectedId);
  const selected: CobranzaFactura | null = selectedId ? (detail.data ?? null) : null;

  const resumenFactura = useFacturaClienteResumen(selected?.factura_id);
  const anuncianteSel = selected ? anuncianteMap.get(selected.anunciante_id) : undefined;
  const metodosPago = useMetodosDePago();
  const pagos = usePagosCliente(selected?.cobranza_id ?? null);

  // Si venimos por deep-link y aún no hay selección, resuelve la cobranza de esa factura.
  const deepLink = useCobranzaFacturaPorFacturaId(facturaIdParam);
  useEffect(() => {
    if (facturaIdParam && !selectedId) {
      const encontrada = deepLink.data?.items?.[0];
      if (encontrada) setSelectedId(encontrada.cobranza_id);
    }
  }, [facturaIdParam, deepLink.data, selectedId]);

  const seleccionar = (cobranzaId: string) => {
    setSelectedId(cobranzaId);
    setModo("ver");
    setSubmitError(null);
    setErrorAccion(null);
  };

  const [diasCredito, setDiasCredito] = useState("");
  const [metodoPagoEdit, setMetodoPagoEdit] = useState("");
  const [comentarios, setComentarios] = useState("");

  const iniciarEdicion = () => {
    if (!selected) return;
    setDiasCredito(String(selected.dias_credito));
    setMetodoPagoEdit(selected.metodo_pago_clave);
    setComentarios(selected.comentarios_cobranza ?? "");
    setModo("editar");
    setErrorAccion(null);
  };

  const guardarEdicion = async () => {
    if (!selected) return;
    setErrorAccion(null);
    try {
      await actualizar.mutateAsync({
        id: selected.cobranza_id,
        data: {
          dias_credito: Number(diasCredito),
          metodo_pago_clave: metodoPagoEdit,
          comentarios_cobranza: comentarios.trim() || null,
        },
      });
      setModo("ver");
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onCrearPago = async (data: PagoClienteCreate) => {
    setSubmitError(null);
    try {
      await pagos.crear.mutateAsync(data);
      setModo("ver");
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const confirmarEliminarPago = async () => {
    if (!pagoAEliminar) return;
    setErrorAccion(null);
    try {
      await pagos.eliminar.mutateAsync(pagoAEliminar.pago_cliente_id);
      setPagoAEliminar(null);
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
      setPagoAEliminar(null);
    }
  };

  let detailNode;
  if (modo === "pagar" && selected) {
    detailNode = (
      <RegistrarPagoForm
        cobranza={selected}
        numeroFactura={selected.numero_factura ?? "—"}
        anunciante={anuncianteSel?.nombre_comercial ?? "—"}
        submitting={pagos.crear.isPending}
        submitError={submitError}
        onConfirm={onCrearPago}
        onCancel={() => {
          setModo("ver");
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const totalFactura = Number(selected.importe_cobrado) + Number(selected.importe_pendiente_cobro);
    const pct = totalFactura > 0 ? (Number(selected.importe_cobrado) / totalFactura) * 100 : 0;
    const diasVenc = diasHasta(selected.fecha_estimada_cobro);
    const listaPagos = pagos.list.data?.items ?? [];

    detailNode = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{selected.numero_factura ?? "—"}</div>
              <div className="dh-sub">
                <span className={`badge ${badgeEstatusCobro(selected.estatus_cobro)}`}>
                  {selected.vencida ? "Vencida" : ESTATUS_COBRO_LABEL[selected.estatus_cobro]}
                </span>
                <span className="badge b-blue">{anuncianteSel?.nombre_comercial ?? "—"}</span>
              </div>
            </div>
            {selected.estatus_cobro !== "cobrada" && (
              <button type="button" className="btn btn-amber btn-sm" onClick={() => setModo("pagar")}>
                + Registrar pago
              </button>
            )}
          </div>
        </div>

        <div className="db">
          <div className="mc-row">
            <div className="mc">
              <div className="mc-lbl">Total factura</div>
              <div className="mc-val">{fmtMoneda(totalFactura.toFixed(2))}</div>
            </div>
            <div className="mc" style={{ background: Number(selected.importe_cobrado) > 0 ? "var(--green-bg)" : undefined }}>
              <div className="mc-lbl">Cobrado</div>
              <div className="mc-val" style={{ color: Number(selected.importe_cobrado) > 0 ? "var(--green-text)" : undefined }}>
                {fmtMoneda(selected.importe_cobrado)}
              </div>
            </div>
            <div
              className="mc"
              style={{
                background:
                  Number(selected.importe_pendiente_cobro) > 0
                    ? selected.vencida
                      ? "var(--red-bg)"
                      : "var(--amber-bg)"
                    : undefined,
              }}
            >
              <div className="mc-lbl">Pendiente</div>
              <div
                className="mc-val"
                style={{ color: selected.vencida ? "var(--red-text)" : Number(selected.importe_pendiente_cobro) > 0 ? "var(--amber-text)" : undefined }}
              >
                {fmtMoneda(selected.importe_pendiente_cobro)}
              </div>
            </div>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div style={{ fontSize: 10, color: "var(--text3)", textAlign: "center", marginBottom: 14 }}>
            {pct.toFixed(0)}% cobrado
          </div>

          <div className="heredado-block">
            <div className="heredado-title">Heredado de factura y anunciante</div>
            <div className="heredado-grid">
              <div className="heredado-row">
                <span className="heredado-lbl">Factura</span>
                <span className="heredado-val mono">{selected.numero_factura ?? "—"}</span>
              </div>
              <div className="heredado-row">
                <span className="heredado-lbl">Concepto</span>
                <span className="heredado-val">{oGuion(resumenFactura.data?.descripcion_factura)}</span>
              </div>
              <div className="heredado-row">
                <span className="heredado-lbl">Razón social</span>
                <span className="heredado-val">{oGuion(resumenFactura.data?.razon_social_facturacion)}</span>
              </div>
              <div className="heredado-row">
                <span className="heredado-lbl">RFC</span>
                <span className="heredado-val mono">{oGuion(anuncianteSel?.rfc_anunciante)}</span>
              </div>
            </div>
          </div>

          <div className="sec">Condiciones de cobro</div>
          {modo === "editar" ? (
            <>
              <div className="r2">
                <div>
                  <div className="fl fl-required">Días de crédito</div>
                  <input
                    className="fi"
                    type="number"
                    min={0}
                    value={diasCredito}
                    onChange={(e) => setDiasCredito(e.target.value)}
                  />
                </div>
                <div>
                  <div className="fl fl-required">Método de pago</div>
                  <select className="fsel" value={metodoPagoEdit} onChange={(e) => setMetodoPagoEdit(e.target.value)}>
                    {(metodosPago.data ?? []).map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.etiqueta}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="fl">Comentarios de cobranza</div>
              <textarea
                className="ftxt"
                value={comentarios}
                onChange={(e) => setComentarios(e.target.value)}
              />
            </>
          ) : (
            <div className="r2">
              <div>
                <div className="fl">
                  Días de crédito <span className="fl-tag her">Heredado, editable</span>
                </div>
                <div className="fv mono">{selected.dias_credito} días</div>
              </div>
              <div>
                <div className="fl">
                  Método de pago <span className="fl-tag her">Heredado</span>
                </div>
                <div className="fv">{selected.metodo_pago_clave}</div>
              </div>
            </div>
          )}
          {modo !== "editar" && (
            <div className="r2">
              <div>
                <div className="fl">Fecha estimada cobro <span className="fl-tag calc">Calc</span></div>
                <div className="fv mono" style={{ color: selected.vencida ? "var(--red-text)" : undefined, fontWeight: 500 }}>
                  {fmtFecha(selected.fecha_estimada_cobro)}
                  {selected.vencida && (
                    <span style={{ fontSize: 10, fontWeight: 600 }}> ({Math.abs(diasVenc)}d vencida)</span>
                  )}
                </div>
              </div>
              {selected.fecha_cobro && (
                <div>
                  <div className="fl">Fecha cobro real</div>
                  <div className="fv mono" style={{ color: "var(--green-text)", fontWeight: 500 }}>
                    {fmtFecha(selected.fecha_cobro)}
                  </div>
                </div>
              )}
            </div>
          )}

          {modo !== "editar" && (
            <>
              <div className="sec">Contacto cobranza</div>
              <div className="fl">Nombre</div>
              <div className="fv">{oGuion(anuncianteSel?.contacto_nombre)}</div>
              <div className="fl">Correo</div>
              <div className="fv link">{oGuion(anuncianteSel?.contacto_email)}</div>
              <div className="fl">Teléfono</div>
              <div className="fv">{oGuion(anuncianteSel?.contacto_telefono)}</div>

              <div className="sec">
                Pagos recibidos ({listaPagos.length})
                {selected.estatus_cobro !== "cobrada" && (
                  <span className="sec-action" onClick={() => setModo("pagar")}>
                    + Registrar pago
                  </span>
                )}
              </div>
              {pagos.list.isLoading && <div className="fv muted">Cargando…</div>}
              {!pagos.list.isLoading && listaPagos.length === 0 && (
                <div className="fv muted">Sin pagos registrados.</div>
              )}
              {listaPagos.map((p) => (
                <div
                  key={p.pago_cliente_id}
                  style={{ border: "1px solid var(--border)", borderRadius: "var(--r)", padding: "9px 12px", marginBottom: 6 }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, color: "var(--green-text)" }}>
                      +{fmtMoneda(p.monto_aplicado)}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text3)" }}>
                        {fmtFecha(p.fecha_pago_cliente)}
                      </span>
                      <button
                        type="button"
                        className="btn btn-xs btn-danger"
                        onClick={() => setPagoAEliminar(p)}
                      >
                        Eliminar
                      </button>
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text2)", display: "flex", justifyContent: "space-between" }}>
                    <span>{p.metodo_pago_clave}</span>
                    <span className="td-mono">{oGuion(p.referencia_pago)}</span>
                  </div>
                </div>
              ))}

              {selected.comentarios_cobranza && (
                <>
                  <div className="sec">Comentarios CxC</div>
                  <div className="fv muted">{selected.comentarios_cobranza}</div>
                </>
              )}
            </>
          )}

          {errorAccion && (
            <div className="state-msg error" style={{ textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
        </div>

        <div className="df">
          {modo === "editar" ? (
            <>
              <button type="button" className="btn btn-sm" onClick={() => setModo("ver")} disabled={actualizar.isPending}>
                Cancelar
              </button>
              <button type="button" className="btn btn-sm btn-phase" onClick={() => void guardarEdicion()} disabled={actualizar.isPending}>
                {actualizar.isPending ? "Guardando…" : "Guardar"}
              </button>
            </>
          ) : selected.estatus_cobro === "cobrada" ? (
            <button type="button" className="btn btn-sm" disabled style={{ opacity: 0.6 }}>
              Factura cobrada
            </button>
          ) : (
            <>
              <button type="button" className="btn btn-sm" onClick={iniciarEdicion}>
                Editar condiciones
              </button>
              <button type="button" className="btn btn-amber btn-sm" onClick={() => setModo("pagar")}>
                + Registrar pago
              </button>
            </>
          )}
        </div>
      </>
    );
  } else {
    detailNode = <DetailEmpty message="Selecciona una cobranza para ver detalle y registrar pagos." />;
  }

  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Factura</th>
            <th>Anunciante</th>
            <th className="td-center">Días cr.</th>
            <th>Fecha estimada</th>
            <th className="td-right">Total</th>
            <th className="td-right">Cobrado</th>
            <th className="td-right">Pendiente</th>
            <th className="td-center">Estado</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => {
            const an = anuncianteMap.get(c.anunciante_id);
            const total = Number(c.importe_cobrado) + Number(c.importe_pendiente_cobro);
            return (
              <tr
                key={c.cobranza_id}
                className={selectedId === c.cobranza_id ? "sel" : ""}
                onClick={() => seleccionar(c.cobranza_id)}
              >
                <td className="td-main mono">{c.numero_factura ?? "—"}</td>
                <td className="td-2">{oGuion(an?.nombre_comercial)}</td>
                <td className="td-center mono">{c.dias_credito}</td>
                <td className="mono" style={{ fontSize: 11 }}>
                  {fmtFecha(c.fecha_estimada_cobro)}
                  {c.vencida && (
                    <div style={{ color: "var(--red-text)", fontSize: 10, fontWeight: 600 }}>
                      <span className={`badge ${BADGE_VENCIDA}`} style={{ padding: "0 5px" }}>
                        Vencida
                      </span>
                    </div>
                  )}
                </td>
                <td className="td-right mono">{fmtMoneda(total.toFixed(2))}</td>
                <td className="td-right mono" style={{ color: Number(c.importe_cobrado) > 0 ? "var(--green-text)" : undefined }}>
                  {Number(c.importe_cobrado) > 0 ? fmtMoneda(c.importe_cobrado) : "—"}
                </td>
                <td className="td-right mono">{Number(c.importe_pendiente_cobro) > 0 ? fmtMoneda(c.importe_pendiente_cobro) : "—"}</td>
                <td className="td-center">
                  <span className={`badge ${badgeEstatusCobro(c.estatus_cobro)}`}>
                    {ESTATUS_COBRO_LABEL[c.estatus_cobro]}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando cobranzas…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las cobranzas.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay cobranzas para el filtro seleccionado.</div>
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
          <div className="cat-title">Cobranza de facturas</div>
          <div className="cat-sub">
            Seguimiento del cobro de cada factura timbrada. Días de crédito heredados del
            anunciante (editables). Permite capturar pagos parciales o totales.
          </div>
        </div>
      </div>

      <div className="kpi-strip">
        <div className="kpi-box">
          <div className="kpi-lbl">Por cobrar</div>
          <div className="kpi-val">{fmtMoneda(kpis.porCobrar.toFixed(2))}</div>
          <div className="kpi-sub">{kpis.totalNoCobradas} facturas</div>
        </div>
        <div className="kpi-box danger">
          <div className="kpi-lbl" style={{ color: "var(--red-text)" }}>Vencido</div>
          <div className="kpi-val" style={{ color: "var(--red-text)" }}>{fmtMoneda(kpis.vencido.toFixed(2))}</div>
          <div className="kpi-sub">{kpis.vencidasCount} facturas vencidas</div>
        </div>
        <div className="kpi-box warn">
          <div className="kpi-lbl" style={{ color: "var(--amber-text)" }}>Vence en 7 días</div>
          <div className="kpi-val" style={{ color: "var(--amber-text)" }}>{fmtMoneda(kpis.porVencer7d.toFixed(2))}</div>
          <div className="kpi-sub">próximas a vencer</div>
        </div>
        <div className="kpi-box success">
          <div className="kpi-lbl" style={{ color: "var(--green-text)" }}>Cobrado este mes</div>
          <div className="kpi-val" style={{ color: "var(--green-text)" }}>{fmtMoneda(kpis.cobradoMes.toFixed(2))}</div>
          <div className="kpi-sub">{kpis.cobradasMesCount} facturas</div>
        </div>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar factura o anunciante…"
        filterLabel="Estado"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setPage(1);
        }}
        count={`${items.length}${ampliando ? "" : ` de ${list.data?.total ?? 0}`}`}
      />

      <ListDetailLayout list={listNode} detail={detailNode} />

      <ConfirmDialog
        visible={!!pagoAEliminar}
        title="Eliminar pago"
        message={
          pagoAEliminar
            ? `¿Eliminar el pago de ${fmtMoneda(pagoAEliminar.monto_aplicado)} del ${fmtFecha(pagoAEliminar.fecha_pago_cliente)}? Si la factura ya estaba cobrada y este pago era necesario para completarla, el backend rechazará la eliminación.`
            : ""
        }
        confirmLabel="Eliminar"
        danger
        loading={pagos.eliminar.isPending}
        onConfirm={() => void confirmarEliminarPago()}
        onCancel={() => setPagoAEliminar(null)}
      />
    </>
  );
}
