/** Facturas de afiliado (F2) — costos que OIR recibe de las emisoras.
 *
 * Captura de CxP. La acción «Autorizar» va por su canal dedicado y solo la puede ejecutar
 * Dirección/Admin (ADR-046): aquí se muestra siempre que el estatus lo permita, y si el
 * área no alcanza el backend responde 403 con un mensaje claro que se pinta tal cual. No
 * se oculta el botón por área: el front no conoce la matriz, y esconderlo daría la falsa
 * impresión de que la acción no existe.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import { FacturaAfiliadoForm } from "../components/FacturaAfiliadoForm";
import { badgeEstatusProveedor, fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useAsignacionesAfiliado, useFacturasAfiliado } from "../../hooks";
import {
  ESTATUS_PROVEEDOR_LABEL,
  type EstatusProveedor,
  type FacturaAfiliado,
  type FacturaAfiliadoCreate,
} from "../../types";

type Filtro = "todas" | EstatusProveedor;

const FILTROS = [
  { key: "todas", label: "Todas" },
  { key: "recibida", label: "Recibidas" },
  { key: "en_revision", label: "En revisión" },
  { key: "autorizada", label: "Autorizadas" },
  { key: "pagada", label: "Pagadas" },
];

export function FacturasAfiliadoPage() {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaAfiliado | null>(null);
  const [creando, setCreando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const filtros = {
    page,
    size,
    q: q || undefined,
    estatus_factura_afiliado: filtro === "todas" ? undefined : filtro,
  };
  const { list, crear, cambiarEstatus, autorizar } = useFacturasAfiliado(filtros);
  const asignaciones = useAsignacionesAfiliado(selected?.factura_afiliado_id ?? null);

  const mensajeDeError = (e: unknown): string =>
    e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

  const ejecutar = async (accion: () => Promise<FacturaAfiliado>) => {
    setErrorAccion(null);
    try {
      setSelected(await accion());
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onCrear = async (data: FacturaAfiliadoCreate) => {
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
      <FacturaAfiliadoForm
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
    const estatus = selected.estatus_factura_afiliado;
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{selected.factura_emisora}</div>
              <div className="dh-sub">{oGuion(selected.razon_social_afiliada)}</div>
            </div>
            <span className={`badge ${badgeEstatusProveedor(estatus)}`}>
              {ESTATUS_PROVEEDOR_LABEL[estatus]}
            </span>
          </div>
        </div>

        <div className="dg">
          <div className="sec">Importes</div>
          <div className="fl">Subtotal</div>
          <div className="fv">{fmtMoneda(selected.monto_factura_afiliado)}</div>
          <div className="fl">IVA</div>
          <div className="fv">{fmtMoneda(selected.iva_factura_afiliado)}</div>
          <div className="fl">Total</div>
          <div className="fv strong">{fmtMoneda(selected.total_factura_afiliado)}</div>
          <div className="fl">Fecha</div>
          <div className="fv">{fmtFecha(selected.fecha_factura_afiliado)}</div>

          <div className="sec">Reparto entre órdenes de estación</div>
          {asignaciones.isLoading && <div className="fv muted">Cargando…</div>}
          {!asignaciones.isLoading && (asignaciones.data?.length ?? 0) === 0 && (
            <div className="fv muted">Sin asignaciones todavía.</div>
          )}
          {(asignaciones.data ?? []).map((a) => (
            <div key={a.id} style={{ display: "contents" }}>
              <div className="fl mono">{a.orden_estacion_id.slice(0, 8)}…</div>
              <div className="fv">{fmtMoneda(a.monto_asignado)}</div>
            </div>
          ))}
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
                      id: selected.factura_afiliado_id,
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
                  onClick={() => ejecutar(() => autorizar.mutateAsync(selected.factura_afiliado_id))}
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
                        id: selected.factura_afiliado_id,
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
                      id: selected.factura_afiliado_id,
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
            <th style={{ width: "22%" }}>Folio emisora</th>
            <th>Afiliado</th>
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
              key={f.factura_afiliado_id}
              className={selected?.factura_afiliado_id === f.factura_afiliado_id ? "sel" : ""}
              onClick={() => {
                setSelected(f);
                setCreando(false);
                setErrorAccion(null);
              }}
            >
              <td className="td-main mono">{f.factura_emisora}</td>
              <td className="td-2">{oGuion(f.razon_social_afiliada)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.total_factura_afiliado)}</td>
              <td className="td-center">
                <span className={`badge ${badgeEstatusProveedor(f.estatus_factura_afiliado)}`}>
                  {ESTATUS_PROVEEDOR_LABEL[f.estatus_factura_afiliado]}
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
          <div className="cat-title">Facturas de afiliado</div>
          <div className="cat-sub">
            Facturas que OIR recibe de las emisoras. Captura de CxP; autorizar es de Dirección.
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
        searchPlaceholder="Buscar por folio de la emisora o razón social…"
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
