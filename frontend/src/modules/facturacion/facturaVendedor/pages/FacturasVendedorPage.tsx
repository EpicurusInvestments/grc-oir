/** Facturas de vendedor (F2) — la comisión que el vendedor PRINCIPAL de la orden cobra
 * a OIR. Entidad nueva, sin equivalente en la spec BD v2: paridad exacta de
 * `FacturasAgenciaPage`, salvo que no hay campos legado `archivo_nombre`/`archivo_path`
 * (esta entidad nace ya con `archivo_pdf_path`/`archivo_xml_path` por separado).
 *
 * Misma máquina de estados y misma regla de autorización que agencia/afiliado.
 * La relación con la OrdenCliente es 1:N — una misma orden puede tener varias facturas
 * de vendedor (parcialidades).
 *
 * Alta y edición comparten el mismo formulario (`FacturaVendedorForm`): la edición
 * puede reasignar vendedor y orden.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, FieldTag, ListDetailLayout, Paginator } from "@/shared/ui";

import { adjuntosFacturacionApi, nombreDeAdjuntoFacturacionRef } from "../../api";
import { badgeEstatusProveedor, fmtFecha, fmtMoneda, fmtPorcentaje, oGuion } from "../../format";
import { useFacturasVendedor } from "../../hooks";
import {
  ESTATUS_PROVEEDOR,
  ESTATUS_PROVEEDOR_LABEL,
  type EstatusProveedor,
  type FacturaVendedor,
  type FacturaVendedorCreate,
  type FacturaVendedorUpdate,
} from "../../types";
import { FacturaVendedorForm } from "../components/FacturaVendedorForm";

/** Solo antes de autorizar (mismo candado que el backend): una factura `autorizada`/
 *  `pagada` ya no se edita. */
const PUEDE_EDITAR = new Set<EstatusProveedor>(["recibida", "en_revision"]);

/** Timeline del ciclo de vida — mismo patrón que `TimelineAgencia`. */
function TimelineVendedor({ estatus }: { estatus: EstatusProveedor }) {
  const actual = ESTATUS_PROVEEDOR.indexOf(estatus);
  return (
    <div className="timeline">
      {ESTATUS_PROVEEDOR.map((paso, i) => (
        <div key={paso} className={`tl-step ${i < actual ? "done" : i === actual ? "current" : ""}`}>
          <div className="tl-dot">{i < actual ? "✓" : i + 1}</div>
          <div className="tl-lbl">{ESTATUS_PROVEEDOR_LABEL[paso]}</div>
        </div>
      ))}
    </div>
  );
}

/** Fila clickeable de un adjunto ya subido (PDF/XML) — descarga vía
 *  `adjuntosFacturacionApi.ver`, mismo mecanismo que en `FacturasAgenciaPage.tsx`. */
function ArchivoDescargable({ etiqueta, archivoRef }: { etiqueta: string; archivoRef: string }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => void adjuntosFacturacionApi.ver(archivoRef)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") void adjuntosFacturacionApi.ver(archivoRef);
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 11px",
        border: "1px solid var(--border)",
        borderRadius: "var(--r)",
        fontSize: 12,
        marginBottom: 5,
        cursor: "pointer",
      }}
    >
      <i className="pi pi-file" aria-hidden="true" />
      <span className="badge b-gray" style={{ fontSize: 10 }}>
        {etiqueta}
      </span>
      {nombreDeAdjuntoFacturacionRef(archivoRef)}
    </div>
  );
}

type Filtro = "todas" | EstatusProveedor;

const FILTROS = [
  { key: "todas", label: "Todas" },
  { key: "recibida", label: "Recibidas" },
  { key: "en_revision", label: "En revisión" },
  { key: "autorizada", label: "Autorizadas" },
  { key: "pagada", label: "Pagadas" },
];

export function FacturasVendedorPage() {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaVendedor | null>(null);
  const [creando, setCreando] = useState(false);
  const [editando, setEditando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const filtros = {
    page,
    size,
    q: q || undefined,
    estatus_factura_vendedor: filtro === "todas" ? undefined : filtro,
  };
  const { list, crear, actualizar, cambiarEstatus, autorizar } = useFacturasVendedor(filtros);

  const mensajeDeError = (e: unknown): string =>
    e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

  const ejecutar = async (accion: () => Promise<FacturaVendedor>) => {
    setErrorAccion(null);
    try {
      setSelected(await accion());
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onCrear = async (data: FacturaVendedorCreate) => {
    setSubmitError(null);
    try {
      setSelected(await crear.mutateAsync(data));
      setCreando(false);
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const onEditar = async (data: FacturaVendedorUpdate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      setSelected(await actualizar.mutateAsync({ id: selected.factura_vendedor_id, data }));
      setEditando(false);
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  let detail;
  if (creando) {
    detail = (
      <FacturaVendedorForm
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={(data) => onCrear(data as FacturaVendedorCreate)}
        onCancel={() => {
          setCreando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (editando && selected) {
    detail = (
      <FacturaVendedorForm
        isEdit
        defaultValues={{
          vendedor_id: selected.vendedor_id,
          orden_id: selected.orden_id,
          folio_factura_vendedor: selected.folio_factura_vendedor ?? undefined,
          fecha_factura_vendedor: selected.fecha_factura_vendedor,
          monto_factura_vendedor: selected.monto_factura_vendedor,
          iva_factura_vendedor: selected.iva_factura_vendedor,
          porcentaje_comision_vendedor: selected.porcentaje_comision_vendedor ?? undefined,
        }}
        archivoPdfPathInicial={selected.archivo_pdf_path}
        archivoXmlPathInicial={selected.archivo_xml_path}
        submitting={actualizar.isPending}
        submitError={submitError}
        onSubmit={(data) => onEditar(data as FacturaVendedorUpdate)}
        onCancel={() => {
          setEditando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const estatus = selected.estatus_factura_vendedor;
    const puedeEditar = PUEDE_EDITAR.has(estatus);
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{oGuion(selected.folio_factura_vendedor)}</div>
              <div className="dh-sub">
                <span className={`badge ${badgeEstatusProveedor(estatus)}`}>
                  {ESTATUS_PROVEEDOR_LABEL[estatus]}
                </span>
                <span className="badge b-teal">{oGuion(selected.vendedor)}</span>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!puedeEditar}
              title={puedeEditar ? undefined : "Una factura autorizada o pagada ya no se puede editar."}
              onClick={() => {
                setEditando(true);
                setSubmitError(null);
              }}
            >
              Editar
            </button>
          </div>
        </div>

        <div className="db">
          <TimelineVendedor estatus={estatus} />

          <div className="mc-row">
            <div className="mc">
              <div className="mc-lbl">Subtotal</div>
              <div className="mc-val">{fmtMoneda(selected.monto_factura_vendedor)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">IVA</div>
              <div className="mc-val">{fmtMoneda(selected.iva_factura_vendedor)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">Total</div>
              <div className="mc-val total">{fmtMoneda(selected.total_factura_vendedor)}</div>
            </div>
          </div>

          <div className="sec">
            Orden relacionada <FieldTag origin="derivado" />
          </div>
          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: "var(--r)",
              padding: "9px 11px",
              marginBottom: 11,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>
                {oGuion(selected.folio_orden)}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>
                {fmtMoneda(selected.orden_total)}
              </span>
            </div>
            {(selected.anunciante || selected.producto) && (
              <div style={{ fontSize: 11, color: "var(--text3)" }}>
                {[selected.anunciante, selected.producto].filter(Boolean).join(" · ")}
              </div>
            )}
          </div>

          <div className="sec">Cálculo de comisión</div>
          <div className="fl">% Comisión aplicada</div>
          <div className="fv mono" style={{ fontSize: 18, fontWeight: 600 }}>
            {fmtPorcentaje(selected.porcentaje_comision_vendedor)}
          </div>
          <div className="fl">
            Monto comisión <FieldTag origin="calculado" />
          </div>
          <div className="fv mono" style={{ fontSize: 18, fontWeight: 600 }}>
            {fmtMoneda(selected.comision_vendedor)}
          </div>
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: -6 }}>
            Sobre venta total c/IVA de la orden ({fmtMoneda(selected.orden_total)})
          </div>

          <div className="sec">Fecha</div>
          <div className="fv mono">{fmtFecha(selected.fecha_factura_vendedor)}</div>

          {(selected.archivo_pdf_path || selected.archivo_xml_path) && (
            <>
              <div className="sec">Archivo</div>
              <div style={{ marginBottom: 6 }}>
                {selected.archivo_pdf_path && (
                  <ArchivoDescargable etiqueta="PDF" archivoRef={selected.archivo_pdf_path} />
                )}
                {selected.archivo_xml_path && (
                  <ArchivoDescargable etiqueta="XML" archivoRef={selected.archivo_xml_path} />
                )}
              </div>
            </>
          )}
        </div>

        <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
          {errorAccion && (
            <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
          {/* Sin botón "Marcar pagada" en `autorizada` — mismo criterio ya aplicado en
              agencia/afiliado: esa transición queda pendiente de resolverse por otro
              canal, no por un botón operativo aquí. */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {estatus === "recibida" && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={cambiarEstatus.isPending}
                onClick={() =>
                  ejecutar(() =>
                    cambiarEstatus.mutateAsync({
                      id: selected.factura_vendedor_id,
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
                  onClick={() => ejecutar(() => autorizar.mutateAsync(selected.factura_vendedor_id))}
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
                        id: selected.factura_vendedor_id,
                        estatus: "recibida",
                      }),
                    )
                  }
                >
                  Devolver a capturista
                </button>
              </>
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
            <th style={{ width: "14%" }}>Folio</th>
            <th style={{ width: "18%" }}>Vendedor</th>
            <th style={{ width: "16%" }}>Orden relacionada</th>
            <th style={{ width: "10%" }}>Fecha</th>
            <th className="td-right" style={{ width: "13%" }}>
              Subtotal
            </th>
            <th className="td-right" style={{ width: "13%" }}>
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
              key={f.factura_vendedor_id}
              className={selected?.factura_vendedor_id === f.factura_vendedor_id ? "sel" : ""}
              onClick={() => {
                setSelected(f);
                setCreando(false);
                setEditando(false);
                setErrorAccion(null);
              }}
            >
              <td className="td-main mono">{oGuion(f.folio_factura_vendedor)}</td>
              <td className="td-2">{oGuion(f.vendedor)}</td>
              <td className="td-2 mono">{oGuion(f.folio_orden)}</td>
              <td className="td-2 mono">{fmtFecha(f.fecha_factura_vendedor)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.monto_factura_vendedor)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.total_factura_vendedor)}</td>
              <td className="td-center">
                <span className={`badge ${badgeEstatusProveedor(f.estatus_factura_vendedor)}`}>
                  {ESTATUS_PROVEEDOR_LABEL[f.estatus_factura_vendedor]}
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
          <div className="cat-title">Facturas de vendedor</div>
          <div className="cat-sub">
            Comisión que el vendedor principal factura a OIR. Una orden puede tener varias.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setSelected(null);
            setCreando(true);
            setEditando(false);
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

      <ListDetailLayout
        list={listNode}
        detail={detail}
        detailWidth={creando || editando ? "560px" : undefined}
      />
    </>
  );
}
