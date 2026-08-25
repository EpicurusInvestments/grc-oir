/** Facturas de agencia (F2) — la comisión que la agencia cobra a OIR.
 *
 * Misma máquina de estados y misma regla de autorización que las de afiliado (ADR-046).
 * La diferencia con `FacturaCliente`: la relación con la OrdenCliente es 1:N — una misma
 * orden puede tener varias facturas de agencia.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import { FacturaAgenciaForm } from "../components/FacturaAgenciaForm";
import { badgeEstatusProveedor, fmtFecha, fmtMoneda, fmtPorcentaje, oGuion } from "../../format";
import { useFacturasAgencia } from "../../hooks";
import {
  ESTATUS_PROVEEDOR_LABEL,
  type EstatusProveedor,
  type FacturaAgencia,
  type FacturaAgenciaCreate,
} from "../../types";

type Filtro = "todas" | EstatusProveedor;

const FILTROS = [
  { key: "todas", label: "Todas" },
  { key: "recibida", label: "Recibidas" },
  { key: "en_revision", label: "En revisión" },
  { key: "autorizada", label: "Autorizadas" },
  { key: "pagada", label: "Pagadas" },
];

export function FacturasAgenciaPage() {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaAgencia | null>(null);
  const [creando, setCreando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const filtros = {
    page,
    size,
    q: q || undefined,
    estatus_factura_agencia: filtro === "todas" ? undefined : filtro,
  };
  const { list, crear, cambiarEstatus, autorizar } = useFacturasAgencia(filtros);

  const mensajeDeError = (e: unknown): string =>
    e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

  const ejecutar = async (accion: () => Promise<FacturaAgencia>) => {
    setErrorAccion(null);
    try {
      setSelected(await accion());
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onCrear = async (data: FacturaAgenciaCreate) => {
    setSubmitError(null);
    try {
      setSelected(await crear.mutateAsync(data));
      setCreando(false);
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  let detail;
  if (creando) {
    detail = (
      <FacturaAgenciaForm
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
    const estatus = selected.estatus_factura_agencia;
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{oGuion(selected.folio_factura_agencia)}</div>
              <div className="dh-sub">Comisión de agencia</div>
            </div>
            <span className={`badge ${badgeEstatusProveedor(estatus)}`}>
              {ESTATUS_PROVEEDOR_LABEL[estatus]}
            </span>
          </div>
        </div>

        <div className="dg">
          <div className="sec">Importes</div>
          <div className="fl">Subtotal</div>
          <div className="fv">{fmtMoneda(selected.monto_factura_agencia)}</div>
          <div className="fl">IVA</div>
          <div className="fv">{fmtMoneda(selected.iva_factura_agencia)}</div>
          <div className="fl">Total</div>
          <div className="fv strong">{fmtMoneda(selected.total_factura_agencia)}</div>

          <div className="sec">Comisión</div>
          <div className="fl">% pactado</div>
          <div className="fv">{fmtPorcentaje(selected.porcentaje_comision_agencia)}</div>
          <div className="fl">Comisión calculada</div>
          <div className="fv">{fmtMoneda(selected.comision_agencia)}</div>
          <div className="fl">Fecha</div>
          <div className="fv">{fmtFecha(selected.fecha_factura_agencia)}</div>
        </div>

        <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
          {errorAccion && (
            <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {estatus === "recibida" && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={cambiarEstatus.isPending}
                onClick={() =>
                  ejecutar(() =>
                    cambiarEstatus.mutateAsync({
                      id: selected.factura_agencia_id,
                      estatus: "en_revision",
                    }),
                  )
                }
              >
                Pasar a revisión
              </button>
            )}
            {estatus === "en_revision" && (
              <>
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={autorizar.isPending}
                  title="Solo Dirección o Admin pueden autorizar"
                  onClick={() => ejecutar(() => autorizar.mutateAsync(selected.factura_agencia_id))}
                >
                  Autorizar
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={cambiarEstatus.isPending}
                  onClick={() =>
                    ejecutar(() =>
                      cambiarEstatus.mutateAsync({
                        id: selected.factura_agencia_id,
                        estatus: "recibida",
                      }),
                    )
                  }
                >
                  Devolver a capturista
                </button>
              </>
            )}
            {estatus === "autorizada" && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={cambiarEstatus.isPending}
                onClick={() =>
                  ejecutar(() =>
                    cambiarEstatus.mutateAsync({
                      id: selected.factura_agencia_id,
                      estatus: "pagada",
                    }),
                  )
                }
              >
                Marcar pagada
              </button>
            )}
          </div>
        </div>
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona una factura para ver el detalle." />;
  }

  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: "22%" }}>Folio</th>
            <th className="td-right" style={{ width: "18%" }}>
              Comisión
            </th>
            <th className="td-right" style={{ width: "20%" }}>
              Total
            </th>
            <th className="td-center" style={{ width: 130 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr
              key={f.factura_agencia_id}
              className={selected?.factura_agencia_id === f.factura_agencia_id ? "sel" : ""}
              onClick={() => {
                setSelected(f);
                setCreando(false);
                setErrorAccion(null);
              }}
            >
              <td className="td-main mono">{oGuion(f.folio_factura_agencia)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.comision_agencia)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.total_factura_agencia)}</td>
              <td className="td-center">
                <span className={`badge ${badgeEstatusProveedor(f.estatus_factura_agencia)}`}>
                  {ESTATUS_PROVEEDOR_LABEL[f.estatus_factura_agencia]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando facturas…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las facturas.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay facturas para el filtro seleccionado.</div>
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
          <div className="cat-title">Facturas de agencia</div>
          <div className="cat-sub">
            Comisión que la agencia factura a OIR. Una orden puede tener varias.
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
          <i className="pi pi-plus" aria-hidden="true" /> Nueva factura
        </button>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar por folio externo…"
        filterLabel="Estatus"
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
