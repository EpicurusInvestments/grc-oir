/** Movimientos bancarios (F3) — cargados por Tesorería para conciliación. Sin matching
 * automático en esta versión (confirmado contra el mockup aprobado): "Conciliar" es un
 * botón manual, de una sola vía.
 */

import { useMemo, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import type { FiltrosMovimientoBancario } from "../../api";
import { badgeConciliado, badgeTipoMovimiento, fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useMovimientosBancarios } from "../../hooks";
import { TIPO_MOVIMIENTO_LABEL, type MovimientoBancario, type MovimientoBancarioCreate } from "../../types";
import { MovimientoBancarioForm } from "../components/MovimientoBancarioForm";

type Filtro = "all" | "sin_conciliar" | "conciliados" | "cargos" | "abonos";

const FILTROS = [
  { key: "all", label: "Todos" },
  { key: "sin_conciliar", label: "Sin conciliar" },
  { key: "conciliados", label: "Conciliados" },
  { key: "abonos", label: "Abonos" },
  { key: "cargos", label: "Cargos" },
];

interface Props {
  filtroInicial?: Filtro;
}

const mensajeDeError = (e: unknown): string =>
  e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

export function MovimientosBancariosPage({ filtroInicial }: Props) {
  const [filtro, setFiltro] = useState<Filtro>(filtroInicial ?? "all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<MovimientoBancario | null>(null);
  const [creando, setCreando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const filtros: FiltrosMovimientoBancario = {
    page,
    size,
    q: q || undefined,
    conciliado: filtro === "sin_conciliar" ? false : filtro === "conciliados" ? true : undefined,
    tipo_movimiento: filtro === "abonos" ? "abono" : filtro === "cargos" ? "cargo" : undefined,
  };

  const { list, crear, conciliar } = useMovimientosBancarios(filtros);
  const items = list.data?.items ?? [];

  const kpis = useMemo(() => {
    const todos = list.data?.items ?? [];
    return {
      totalAbonos: todos.filter((m) => m.tipo_movimiento === "abono").reduce((s, m) => s + Number(m.monto_movimiento), 0),
      countAbonos: todos.filter((m) => m.tipo_movimiento === "abono").length,
      totalCargos: todos.filter((m) => m.tipo_movimiento === "cargo").reduce((s, m) => s + Number(m.monto_movimiento), 0),
      countCargos: todos.filter((m) => m.tipo_movimiento === "cargo").length,
      sinConciliar: todos.filter((m) => !m.conciliado).length,
    };
  }, [list.data]);

  const seleccionar = (m: MovimientoBancario) => {
    setSelected(m);
    setCreando(false);
    setErrorAccion(null);
  };

  const onCrear = async (data: MovimientoBancarioCreate) => {
    setSubmitError(null);
    try {
      setSelected(await crear.mutateAsync(data));
      setCreando(false);
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const onConciliar = async (id: string) => {
    setErrorAccion(null);
    try {
      setSelected(await conciliar.mutateAsync(id));
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  let detail;
  if (creando) {
    detail = (
      <MovimientoBancarioForm
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
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div
                className="dh-name mono"
                style={{ color: selected.tipo_movimiento === "abono" ? "var(--green-text)" : "var(--amber-text)" }}
              >
                {selected.tipo_movimiento === "abono" ? "+" : "−"}
                {fmtMoneda(selected.monto_movimiento)}
              </div>
              <div className="dh-sub">
                <span className={`badge ${badgeTipoMovimiento(selected.tipo_movimiento)}`}>
                  {TIPO_MOVIMIENTO_LABEL[selected.tipo_movimiento]}
                </span>
                <span className={`badge ${badgeConciliado(selected.conciliado)}`}>
                  {selected.conciliado ? "✓ Conciliado" : "⚠ Pendiente"}
                </span>
              </div>
            </div>
          </div>
        </div>
        <div className="db">
          <div className="sec">Datos</div>
          <div className="fl">Fecha</div>
          <div className="fv mono">{fmtFecha(selected.fecha_movimiento)}</div>
          <div className="fl">Tipo</div>
          <div className="fv">{selected.tipo_movimiento === "abono" ? "Abono (entrada)" : "Cargo (salida)"}</div>
          <div className="fl">Monto</div>
          <div
            className="fv mono big"
            style={{ color: selected.tipo_movimiento === "abono" ? "var(--green-text)" : "var(--amber-text)" }}
          >
            {selected.tipo_movimiento === "abono" ? "+" : "−"}
            {fmtMoneda(selected.monto_movimiento)}
          </div>
          <div className="fl">Referencia bancaria</div>
          <div className="fv mono">{oGuion(selected.referencia_bancaria)}</div>
          <div className="fl">Concepto</div>
          <div className="fv muted">{oGuion(selected.descripcion_movimiento)}</div>
          {selected.archivo_nombre && (
            <>
              <div className="fl">Estado de cuenta</div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 11px",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r)",
                  fontSize: 12,
                }}
              >
                {selected.archivo_nombre}
              </div>
            </>
          )}
          {!selected.conciliado && (
            <>
              <div className="sec">Conciliación</div>
              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 8 }}>
                Sin matching automático en esta versión — confirma manualmente contra el
                estado de cuenta.
              </div>
            </>
          )}
          {errorAccion && (
            <div className="state-msg error" style={{ textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
        </div>
        <div className="df">
          {selected.conciliado ? (
            <button type="button" className="btn btn-sm" disabled style={{ opacity: 0.6 }}>
              Conciliado
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-sm btn-phase"
              disabled={conciliar.isPending}
              title="Solo Tesorería o Admin pueden conciliar"
              onClick={() => void onConciliar(selected.movimiento_id)}
            >
              Marcar conciliado
            </button>
          )}
        </div>
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona un movimiento para ver el detalle." />;
  }

  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Tipo</th>
            <th className="td-right">Monto</th>
            <th>Referencia</th>
            <th>Descripción</th>
            <th className="td-center">Concilia</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m) => (
            <tr
              key={m.movimiento_id}
              className={selected?.movimiento_id === m.movimiento_id ? "sel" : ""}
              onClick={() => seleccionar(m)}
            >
              <td className="mono" style={{ fontSize: 11 }}>{fmtFecha(m.fecha_movimiento)}</td>
              <td>
                <span className={`badge ${badgeTipoMovimiento(m.tipo_movimiento)}`}>
                  {TIPO_MOVIMIENTO_LABEL[m.tipo_movimiento]}
                </span>
              </td>
              <td
                className="td-right mono"
                style={{ fontWeight: 600, color: m.tipo_movimiento === "abono" ? "var(--green-text)" : "var(--amber-text)" }}
              >
                {m.tipo_movimiento === "abono" ? "+" : "−"}
                {fmtMoneda(m.monto_movimiento)}
              </td>
              <td className="mono" style={{ fontSize: 11 }}>{oGuion(m.referencia_bancaria)}</td>
              <td className="td-main" style={{ fontSize: 12 }}>{oGuion(m.descripcion_movimiento)}</td>
              <td className="td-center">
                <span className={`badge ${badgeConciliado(m.conciliado)}`}>
                  {m.conciliado ? "✓ Conciliado" : "⚠ Pendiente"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando movimientos…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los movimientos.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay movimientos para el filtro seleccionado.</div>
      )}
      {list.data && list.data.total > 0 && (
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
          <div className="cat-title">Movimientos bancarios</div>
          <div className="cat-sub">
            Movimientos cargados por Tesorería para conciliación. Los abonos se
            reconcilian con pagos del cliente; los cargos con requisiciones pagadas.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-phase"
          title="Solo Tesorería o Admin pueden capturar"
          onClick={() => {
            setSelected(null);
            setCreando(true);
            setSubmitError(null);
          }}
        >
          <i className="pi pi-plus" aria-hidden="true" /> Nuevo movimiento
        </button>
      </div>

      <div className="kpi-strip">
        <div className="kpi-box success">
          <div className="kpi-lbl" style={{ color: "var(--green-text)" }}>Total abonos</div>
          <div className="kpi-val" style={{ color: "var(--green-text)" }}>{fmtMoneda(String(kpis.totalAbonos))}</div>
          <div className="kpi-sub">{kpis.countAbonos} entradas</div>
        </div>
        <div className="kpi-box">
          <div className="kpi-lbl">Total cargos</div>
          <div className="kpi-val">{fmtMoneda(String(kpis.totalCargos))}</div>
          <div className="kpi-sub">{kpis.countCargos} salidas</div>
        </div>
        <div className={`kpi-box${kpis.sinConciliar > 0 ? " danger" : ""}`}>
          <div className="kpi-lbl" style={kpis.sinConciliar > 0 ? { color: "var(--red-text)" } : undefined}>
            Sin conciliar
          </div>
          <div className="kpi-val" style={kpis.sinConciliar > 0 ? { color: "var(--red-text)" } : undefined}>
            {kpis.sinConciliar}
          </div>
          <div className="kpi-sub">movimientos por revisar</div>
        </div>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar referencia o descripción…"
        filterLabel="Estado"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setPage(1);
        }}
        count={list.data ? `${items.length} de ${list.data.total}` : undefined}
      />

      <ListDetailLayout list={listNode} detail={detail} />
    </>
  );
}
