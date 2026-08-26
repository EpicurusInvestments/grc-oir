/** Costos adicionales (F2) — nómina y overhead.
 *
 * Sin máquina de estados: es un registro simple (la spec no le define ningún estatus).
 * `orden_id` es opcional: NULL = costo general del área, no imputado a una venta.
 *
 * Alimentan el Estado de Resultados de F4; hoy solo se capturan y consultan.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import { CostoForm } from "../components/CostoForm";
import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useCostos } from "../../hooks";
import { TIPO_COSTO_LABEL, type CostoAdicional, type CostoAdicionalCreate } from "../../types";

type Filtro = "todos" | "nomina" | "overhead";

const FILTROS = [
  { key: "todos", label: "Todos" },
  { key: "nomina", label: "Nómina" },
  { key: "overhead", label: "Overhead" },
];

export function CostosPage() {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<CostoAdicional | null>(null);
  const [creando, setCreando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const filtros = {
    page,
    size,
    q: q || undefined,
    tipo_costo: filtro === "todos" ? undefined : filtro,
  };
  const { list, crear } = useCostos(filtros);

  const onCrear = async (data: CostoAdicionalCreate) => {
    setSubmitError(null);
    try {
      setSelected(await crear.mutateAsync(data));
      setCreando(false);
    } catch (e) {
      setSubmitError(
        e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.",
      );
    }
  };

  let detail;
  if (creando) {
    detail = (
      <CostoForm
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
              <div className="dh-name">{selected.descripcion_costo}</div>
              <div className="dh-sub">Periodo {selected.periodo_contable}</div>
            </div>
            <span className="badge b-gray">{TIPO_COSTO_LABEL[selected.tipo_costo]}</span>
          </div>
        </div>

        <div className="dg">
          <div className="sec">Costo</div>
          <div className="fl">Monto</div>
          <div className="fv strong">{fmtMoneda(selected.monto_costo)}</div>
          <div className="fl">Periodo contable</div>
          <div className="fv mono">{selected.periodo_contable}</div>
          <div className="fl">Orden asociada</div>
          <div className="fv muted">
            {selected.orden_id ? selected.orden_id.slice(0, 8) + "…" : "Costo general (sin orden)"}
          </div>

          <div className="sec">Respaldo</div>
          <div className="fl">Archivo</div>
          <div className="fv muted">{oGuion(selected.archivo_nombre)}</div>

          <div className="sec">Registro</div>
          <div className="fl">Capturado</div>
          <div className="fv muted">{fmtFecha(selected.created_at)}</div>
        </div>
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona un costo para ver el detalle." />;
  }

  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Descripción</th>
            <th style={{ width: "14%" }}>Periodo</th>
            <th className="td-right" style={{ width: "20%" }}>
              Monto
            </th>
            <th className="td-center" style={{ width: 110 }}>
              Tipo
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr
              key={c.costo_id}
              className={selected?.costo_id === c.costo_id ? "sel" : ""}
              onClick={() => {
                setSelected(c);
                setCreando(false);
              }}
            >
              <td className="td-main">{c.descripcion_costo}</td>
              <td className="td-2 mono">{c.periodo_contable}</td>
              <td className="td-2 td-right">{fmtMoneda(c.monto_costo)}</td>
              <td className="td-center">
                <span className="badge b-gray">{TIPO_COSTO_LABEL[c.tipo_costo]}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando costos…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los costos.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay costos para el filtro seleccionado.</div>
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
          <div className="cat-title">Costos adicionales</div>
          <div className="cat-sub">
            Nómina (formato NOI) y overhead. Alimentan el Estado de Resultados de F4.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setSelected(null);
            setCreando(true);
            setSubmitError(null);
          }}
        >
          <i className="pi pi-plus" aria-hidden="true" /> Nuevo costo
        </button>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar por descripción…"
        filterLabel="Tipo"
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
