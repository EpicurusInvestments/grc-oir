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

import { adjuntosFacturacionApi, nombreDeAdjuntoFacturacionRef } from "../../api";
import { FacturaAfiliadoForm } from "../components/FacturaAfiliadoForm";
import { badgeEstatusProveedor, fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useAsignacionesAfiliado, useFacturasAfiliado } from "../../hooks";
import {
  ESTATUS_PROVEEDOR,
  ESTATUS_PROVEEDOR_LABEL,
  type EstatusProveedor,
  type FacturaAfiliado,
  type FacturaAfiliadoCreate,
  type FacturaAfiliadoUpdate,
} from "../../types";

/** Solo antes de autorizar (mismo candado que el backend, `FacturaAfiliadoService.update`):
 *  una factura `autorizada`/`pagada` ya no se edita. */
const PUEDE_EDITAR = new Set<EstatusProveedor>(["recibida", "en_revision"]);

/** Timeline del ciclo de vida (mismo patrón que `Timeline` de Facturas al cliente):
 *  `ESTATUS_PROVEEDOR` ya está en orden y sin "cancelada" (esta entidad no la tiene). */
function TimelineAfiliado({ estatus }: { estatus: EstatusProveedor }) {
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
 *  `adjuntosFacturacionApi.ver`, mismo mecanismo que `AdjuntoFacturaInput` en modo lectura. */
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

export function FacturasAfiliadoPage() {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaAfiliado | null>(null);
  const [creando, setCreando] = useState(false);
  const [editando, setEditando] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const filtros = {
    page,
    size,
    q: q || undefined,
    estatus_factura_afiliado: filtro === "todas" ? undefined : filtro,
  };
  const { list, crear, actualizar, cambiarEstatus, autorizar } = useFacturasAfiliado(filtros);
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

  const onEditar = async (data: FacturaAfiliadoUpdate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      setSelected(await actualizar.mutateAsync({ id: selected.factura_afiliado_id, data }));
      setEditando(false);
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
        onSubmit={(data) => onCrear(data as FacturaAfiliadoCreate)}
        onCancel={() => {
          setCreando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (editando && selected) {
    detail = (
      <FacturaAfiliadoForm
        isEdit
        defaultValues={{
          afiliado_id: selected.afiliado_id,
          factura_emisora: selected.factura_emisora,
          fecha_factura_afiliado: selected.fecha_factura_afiliado,
          monto_factura_afiliado: selected.monto_factura_afiliado,
          iva_factura_afiliado: selected.iva_factura_afiliado,
        }}
        archivoPdfPathInicial={selected.archivo_pdf_path}
        archivoXmlPathInicial={selected.archivo_xml_path}
        submitting={actualizar.isPending}
        submitError={submitError}
        onSubmit={(data) => onEditar(data as FacturaAfiliadoUpdate)}
        onCancel={() => {
          setEditando(false);
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const estatus = selected.estatus_factura_afiliado;
    const puedeEditar = PUEDE_EDITAR.has(estatus);
    const asignado = (asignaciones.data ?? []).reduce((s, a) => s + Number(a.monto_asignado), 0);
    const sinAsignar = Number(selected.monto_factura_afiliado) - asignado;
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name mono">{selected.factura_emisora}</div>
              <div className="dh-sub">
                <span className={`badge ${badgeEstatusProveedor(estatus)}`}>
                  {ESTATUS_PROVEEDOR_LABEL[estatus]}
                </span>
                <span className="badge b-teal">{oGuion(selected.razon_social_afiliada)}</span>
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
          <TimelineAfiliado estatus={estatus} />

          <div className="mc-row">
            <div className="mc">
              <div className="mc-lbl">Subtotal</div>
              <div className="mc-val">{fmtMoneda(selected.monto_factura_afiliado)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">IVA</div>
              <div className="mc-val">{fmtMoneda(selected.iva_factura_afiliado)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">Total</div>
              <div className="mc-val total">{fmtMoneda(selected.total_factura_afiliado)}</div>
            </div>
          </div>

          <div className="sec">Datos generales</div>
          <div className="fl">Razón social emisora</div>
          <div className="fv">{oGuion(selected.razon_social_afiliada)}</div>
          <div className="r2">
            <div>
              <div className="fl">Folio</div>
              <div className="fv mono">{selected.factura_emisora}</div>
            </div>
            <div>
              <div className="fl">Fecha</div>
              <div className="fv mono">{fmtFecha(selected.fecha_factura_afiliado)}</div>
            </div>
          </div>
          {(selected.archivo_pdf_path || selected.archivo_xml_path || selected.archivo_nombre) && (
            <>
              <div className="fl">Archivo</div>
              <div style={{ marginBottom: 6 }}>
                {selected.archivo_pdf_path && (
                  <ArchivoDescargable etiqueta="PDF" archivoRef={selected.archivo_pdf_path} />
                )}
                {selected.archivo_xml_path && (
                  <ArchivoDescargable etiqueta="XML" archivoRef={selected.archivo_xml_path} />
                )}
                {/* Legado: facturas capturadas antes de separar PDF/XML (ADR nuevo). */}
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

          <div className="sec">Asignación a órdenes estación</div>
          <div style={{ display: "flex", gap: 8, marginBottom: 11 }}>
            <div style={{ flex: 1, background: "var(--surface2)", borderRadius: "var(--r)", padding: "8px 11px" }}>
              <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Asignado
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600 }}>{fmtMoneda(String(asignado))}</div>
            </div>
            <div
              style={{
                flex: 1,
                background: sinAsignar === 0 ? "var(--green-bg)" : "var(--red-bg)",
                borderRadius: "var(--r)",
                padding: "8px 11px",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: sinAsignar === 0 ? "var(--green-text)" : "var(--red-text)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                Sin asignar
              </div>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 14,
                  fontWeight: 600,
                  color: sinAsignar === 0 ? "var(--green-text)" : "var(--red-text)",
                }}
              >
                {fmtMoneda(String(sinAsignar))}
              </div>
            </div>
          </div>
          {asignaciones.isLoading && <div className="fv muted">Cargando…</div>}
          {!asignaciones.isLoading && (asignaciones.data?.length ?? 0) === 0 && (
            <div className="fv muted" style={{ fontSize: 12 }}>
              Sin asignaciones. Asigna esta factura a las órdenes estación correspondientes.
            </div>
          )}
          {(asignaciones.data ?? []).map((a) => (
            <div
              key={a.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                padding: "9px 11px",
                marginBottom: 5,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>
                  {a.orden_estacion_id.slice(0, 8)}…
                </span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>
                  {fmtMoneda(a.monto_asignado)}
                </span>
              </div>
              {a.notas_asignacion && (
                <div style={{ fontSize: 11, color: "var(--text3)" }}>{a.notas_asignacion}</div>
              )}
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
                setEditando(false);
                setErrorAccion(null);
              }}
            >
              <td className="td-main mono">{f.factura_emisora}</td>
              <td className="td-2">{oGuion(f.razon_social_afiliada)}</td>
              <td className="td-2 td-right">{fmtMoneda(f.total_factura_afiliado, { truncar: true })}</td>
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

      {/* Más ancho al capturar/editar: lo justo para que "Cargar PDF de la factura" /
          "Cargar XML de la factura" quepan lado a lado sin cortarse — no más que eso,
          para no dejar el formulario con espacio de sobra (fix: 760px quedaba muy largo). */}
      <ListDetailLayout list={listNode} detail={detail} detailWidth={creando || editando ? "560px" : undefined} />
    </>
  );
}
