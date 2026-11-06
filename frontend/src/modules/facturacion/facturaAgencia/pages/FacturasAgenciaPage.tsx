/** Facturas de agencia (F2) — la comisión que la agencia cobra a OIR.
 *
 * Misma máquina de estados y misma regla de autorización que las de afiliado (ADR-046).
 *
 * ADR nuevo (petición del usuario, con captura, 2026-11-06) — SUSTITUYE el criterio de
 * ADR-079: la relación con OrdenCliente pasa de 1:1-por-factura a N:M vía
 * `FacturaAgenciaOrden`, mismo patrón que `FacturaAfiliado` — una factura de agencia
 * acumula VARIAS órdenes, cada una con su propio % ya pactado.
 *
 * Alta y edición comparten el mismo formulario (`FacturaAgenciaForm`), igual criterio
 * que `FacturasAfiliadoPage` desde ADR-087: la edición puede reasignar agencia y editar
 * qué órdenes tiene asignadas.
 *
 * PDF/XML de la factura (ADR-079, mismo mecanismo que ADR-070 en Afiliado): se muestran
 * como `ArchivoDescargable` en la sección "Archivo" del detalle.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, FieldTag, ListDetailLayout, Paginator } from "@/shared/ui";

import { adjuntosFacturacionApi, nombreDeAdjuntoFacturacionRef } from "../../api";
import { FacturaAgenciaForm } from "../components/FacturaAgenciaForm";
import { badgeEstatusProveedor, fmtFecha, fmtMoneda, fmtPorcentaje, oGuion } from "../../format";
import { useFacturasAgencia, useOrdenesAgencia } from "../../hooks";
import {
  ESTATUS_PROVEEDOR,
  ESTATUS_PROVEEDOR_LABEL,
  type EstatusProveedor,
  type FacturaAgencia,
  type FacturaAgenciaCreate,
  type FacturaAgenciaUpdate,
} from "../../types";

/** Solo antes de autorizar (mismo candado que el backend): una factura `autorizada`/
 *  `pagada` ya no se edita. */
const PUEDE_EDITAR = new Set<EstatusProveedor>(["recibida", "en_revision"]);

/** Timeline del ciclo de vida — mismo patrón que `TimelineAfiliado`
 *  (`facturaAfiliado/pages/FacturasAfiliadoPage.tsx`): `ESTATUS_PROVEEDOR` ya está en
 *  orden y sin "cancelada" (esta entidad no la tiene). */
function TimelineAgencia({ estatus }: { estatus: EstatusProveedor }) {
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
 *  `adjuntosFacturacionApi.ver`, mismo mecanismo que en `FacturasAfiliadoPage.tsx`. */
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

export function FacturasAgenciaPage() {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaAgencia | null>(null);
  const [creando, setCreando] = useState(false);
  const [editando, setEditando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const filtros = {
    page,
    size,
    q: q || undefined,
    estatus_factura_agencia: filtro === "todas" ? undefined : filtro,
  };
  const { list, crear, actualizar, cambiarEstatus, autorizar } = useFacturasAgencia(filtros);
  const ordenes = useOrdenesAgencia(selected?.factura_agencia_id ?? null);

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

  const onEditar = async (data: FacturaAgenciaUpdate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      setSelected(await actualizar.mutateAsync({ id: selected.factura_agencia_id, data }));
      setEditando(false);
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
        onSubmit={(data) => onCrear(data as FacturaAgenciaCreate)}
        onCancel={() => {
          setCreando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (editando && selected) {
    detail = (
      <FacturaAgenciaForm
        isEdit
        defaultValues={{
          agencia_id: selected.agencia_id,
          folio_factura_agencia: selected.folio_factura_agencia ?? undefined,
          fecha_factura_agencia: selected.fecha_factura_agencia,
        }}
        ordenesIniciales={ordenes.data ?? []}
        archivoPdfPathInicial={selected.archivo_pdf_path}
        archivoXmlPathInicial={selected.archivo_xml_path}
        submitting={actualizar.isPending}
        submitError={submitError}
        onSubmit={(data) => onEditar(data as FacturaAgenciaUpdate)}
        onCancel={() => {
          setEditando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const estatus = selected.estatus_factura_agencia;
    const puedeEditar = PUEDE_EDITAR.has(estatus);
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{oGuion(selected.folio_factura_agencia)}</div>
              <div className="dh-sub">
                <span className={`badge ${badgeEstatusProveedor(estatus)}`}>
                  {ESTATUS_PROVEEDOR_LABEL[estatus]}
                </span>
                <span className="badge b-teal">{oGuion(selected.agencia)}</span>
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
          <TimelineAgencia estatus={estatus} />

          <div className="mc-row">
            <div className="mc">
              <div className="mc-lbl">Subtotal</div>
              <div className="mc-val">{fmtMoneda(selected.monto_factura_agencia)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">IVA</div>
              <div className="mc-val">{fmtMoneda(selected.iva_factura_agencia)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">Total</div>
              <div className="mc-val total">{fmtMoneda(selected.total_factura_agencia)}</div>
            </div>
          </div>

          <div className="sec">
            Órdenes asignadas <FieldTag origin="derivado" />
          </div>
          {ordenes.isLoading && <div className="fv muted">Cargando…</div>}
          {!ordenes.isLoading && (ordenes.data?.length ?? 0) === 0 && (
            <div className="fv muted" style={{ fontSize: 12 }}>
              Sin órdenes asignadas.
            </div>
          )}
          {(ordenes.data ?? []).map((o) => (
            <div
              key={o.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                padding: "9px 11px",
                marginBottom: 5,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>
                  {oGuion(o.folio_orden)}
                </span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>
                  {fmtMoneda(o.comision_calculada)}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "var(--text3)" }}>
                {fmtPorcentaje(o.porcentaje_comision_snap)} sobre {fmtMoneda(o.orden_total)}
                {o.anunciante ? ` · ${o.anunciante}` : ""}
              </div>
            </div>
          ))}

          <div className="sec">Fecha</div>
          <div className="fv mono">{fmtFecha(selected.fecha_factura_agencia)}</div>

          {(selected.archivo_pdf_path || selected.archivo_xml_path || selected.archivo_nombre) && (
            <>
              <div className="sec">Archivo</div>
              <div style={{ marginBottom: 6 }}>
                {selected.archivo_pdf_path && (
                  <ArchivoDescargable etiqueta="PDF" archivoRef={selected.archivo_pdf_path} />
                )}
                {selected.archivo_xml_path && (
                  <ArchivoDescargable etiqueta="XML" archivoRef={selected.archivo_xml_path} />
                )}
                {/* Legado: facturas capturadas antes de separar PDF/XML. */}
                {selected.archivo_nombre && !selected.archivo_pdf_path && !selected.archivo_xml_path && (
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
                    <i className="pi pi-file" aria-hidden="true" />
                    {selected.archivo_nombre}
                  </div>
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
              FacturasAfiliadoPage: esa transición queda pendiente de resolverse por
              otro canal (p.ej. Requisiciones en F3), no por un botón operativo aquí. */}
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
            <th style={{ width: "18%" }}>Agencia</th>
            <th style={{ width: "10%" }}>Fecha</th>
            <th className="td-right" style={{ width: "13%" }}>
              Subtotal
            </th>
            <th className="td-right" style={{ width: "13%" }}>
              Total
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Órdenes asig.
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
                setEditando(false);
                setErrorAccion(null);
              }}
            >
              <td className="td-main mono">{oGuion(f.folio_factura_agencia)}</td>
              <td className="td-2">{oGuion(f.agencia)}</td>
              <td className="td-2 mono">{fmtFecha(f.fecha_factura_agencia)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.monto_factura_agencia)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.total_factura_agencia)}</td>
              <td className="td-center">{f.ordenes_asignadas}</td>
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
