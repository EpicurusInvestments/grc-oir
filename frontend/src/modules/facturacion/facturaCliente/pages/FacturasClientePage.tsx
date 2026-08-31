/** Facturas al cliente (F2) — lista + panel de detalle.
 *
 * Estructura tomada de la pantalla aprobada `Fase_2_-_Facturacion.html`: la tabla lleva
 * 8 columnas (número, pedido, receptor, emisora, fecha, total, folio fiscal y estado) y
 * el panel abre con el timeline del ciclo de vida y las tres tarjetas de importes ANTES de
 * cualquier otro dato. Los filtros son los del prototipo más «Entregadas» (pedido del
 * equipo): agrupan estados, no hay uno por cada uno.
 *
 * Las acciones se muestran SOLO cuando la transición es válida desde el estado actual: la
 * UI no ofrece un botón que el servidor rechazaría con 409. El backend valida siempre —
 * esto es UX.
 *
 * Timbrar y cancelar tienen efecto colateral sobre la `OrdenCliente` (el handoff de F2 y
 * su reversión, ADR-047). Ambos lo advierten, porque desde esta pantalla no se ve la orden
 * que se está moviendo.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, FieldTag, ListDetailLayout, Paginator } from "@/shared/ui";

import { RegistrarTimbradoForm } from "../components/RegistrarTimbradoForm";
import { facturaClienteApi } from "../../api";
import { badgeEstadoFactura, fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useFacturasCliente, useOrdenesPorFacturar } from "../../hooks";
import {
  ESTADO_FACTURACION_LABEL,
  FLUJO_FACTURACION,
  type EstadoFacturacion,
  type FacturaCliente,
  type TimbrarInput,
} from "../../types";

/** Filtros de la pantalla aprobada, más «Entregadas» (pedido del equipo): sigue sin haber
 *  uno por cada estado — «Pendientes timbrar» agrupa `preparada` y `enviada_a_timbrado`. */
type Filtro = "todas" | "pendientes_timbrar" | "timbradas" | "entregadas" | "cobradas";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "pendientes_timbrar", label: "Pendientes timbrar" },
  { key: "timbradas", label: "Timbradas" },
  { key: "entregadas", label: "Entregadas" },
  { key: "cobradas", label: "Cobradas" },
];

/** Filtros que el BACKEND resuelve por estado. `pendientes_timbrar` no está aquí: agrupa
 *  dos estados y la API filtra por uno solo, así que se resuelve en el cliente. */
const ESTADO_POR_FILTRO: Partial<Record<Filtro, EstadoFacturacion>> = {
  timbradas: "timbrada",
  entregadas: "entregada",
  cobradas: "cobrada",
};

/** Etiquetas del timeline; el prototipo abrevia el primer paso a "Prep.". */
const PASO_LABEL: Record<(typeof FLUJO_FACTURACION)[number], string> = {
  preparada: "Prep.",
  enviada_a_timbrado: "Enviada",
  timbrada: "Timbrada",
  entregada: "Entregada",
  cobrada: "Cobrada",
};

/** Ciclo de vida de la factura, gemelo del timeline de F1. */
function Timeline({ estado }: { estado: EstadoFacturacion }) {
  if (estado === "cancelada") {
    return (
      <div className="state-msg" style={{ margin: "8px 0 14px" }}>
        Factura cancelada
      </div>
    );
  }
  const actual = FLUJO_FACTURACION.indexOf(estado as (typeof FLUJO_FACTURACION)[number]);
  return (
    <div className="timeline">
      {FLUJO_FACTURACION.map((paso, i) => (
        <div key={paso} className={`tl-step ${i < actual ? "done" : i === actual ? "current" : ""}`}>
          <div className="tl-dot">{i < actual ? "✓" : i + 1}</div>
          <div className="tl-lbl">{PASO_LABEL[paso]}</div>
        </div>
      ))}
    </div>
  );
}

interface Props {
  onIrAListasParaFacturar: () => void;
}

export function FacturasClientePage({ onIrAListasParaFacturar }: Props) {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaCliente | null>(null);
  const [modo, setModo] = useState<"view" | "timbrar">("view");
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [faltantes, setFaltantes] = useState<string[] | null>(null);

  // "Pendientes timbrar" agrupa los DOS estados previos al folio fiscal; el backend filtra
  // por un solo estado, así que ese filtro se resuelve sobre la página ya cargada.
  const filtros = {
    page,
    size,
    q: q || undefined,
    estado_facturacion: ESTADO_POR_FILTRO[filtro],
  };
  const { list, enviarATimbrado, timbrar, entregar, cancelar } = useFacturasCliente(filtros);
  // Solo para saber si queda algo por facturar y así habilitar/inhabilitar el botón del
  // header — la bandeja en sí vive en «Listas para facturar» (ADR pendiente de numerar).
  const porFacturar = useOrdenesPorFacturar({ page: 1, size: 1 });
  const hayOrdenesPorFacturar = (porFacturar.data?.total ?? 0) > 0;

  const mensajeDeError = (e: unknown): string =>
    e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

  const seleccionar = (f: FacturaCliente) => {
    setSelected(f);
    setModo("view");
    setErrorAccion(null);
    setFaltantes(null);
  };

  const ejecutar = async (accion: () => Promise<FacturaCliente>) => {
    setErrorAccion(null);
    try {
      setSelected(await accion());
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const descargarArchivo = async (f: FacturaCliente) => {
    setErrorAccion(null);
    setFaltantes(null);
    try {
      // El backend genera el archivo aunque falten campos fiscales: sirve para revisarlo.
      // Lo que NO puede pasar es que alguien lo mande al PAC sin saber que va incompleto.
      setFaltantes(await facturaClienteApi.descargarArchivoPlano(f.factura_id, f.numero_factura));
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onTimbrar = async (data: TimbrarInput) => {
    if (!selected) return;
    setErrorAccion(null);
    try {
      setSelected(await timbrar.mutateAsync({ id: selected.factura_id, data }));
      setModo("view");
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  // ── panel de detalle ────────────────────────────────────────────────────────
  let detail;
  if (modo === "timbrar" && selected) {
    detail = (
      <RegistrarTimbradoForm
        numeroFactura={selected.numero_factura}
        submitting={timbrar.isPending}
        submitError={errorAccion}
        onConfirm={onTimbrar}
        onCancel={() => {
          setModo("view");
          setErrorAccion(null);
        }}
      />
    );
  } else if (selected) {
    const estado = selected.estado_facturacion;
    const timbrada = ["timbrada", "entregada", "cobrada"].includes(estado);
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.numero_factura}</div>
              <div className="dh-sub" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span className={`badge ${badgeEstadoFactura(estado)}`}>
                  {ESTADO_FACTURACION_LABEL[estado]}
                </span>
                <span className="badge b-blue">{selected.razon_social_facturacion}</span>
                {selected.folio_orden && (
                  <span className="badge b-blue mono">{selected.folio_orden}</span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="db">
          <Timeline estado={estado} />

          <div className="mc-row">
            <div className="mc">
              <div className="mc-lbl">Subtotal</div>
              <div className="mc-val">{fmtMoneda(selected.subtotal_factura)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">IVA</div>
              <div className="mc-val">{fmtMoneda(selected.iva_factura)}</div>
            </div>
            <div className="mc">
              <div className="mc-lbl">Total</div>
              <div className="mc-val total">{fmtMoneda(selected.total_factura)}</div>
            </div>
          </div>

          <div className="sec">Identificación</div>
          <div className="r2">
            <div>
              <div className="fl">No. factura</div>
              <div className="fv mono">{selected.numero_factura}</div>
            </div>
            <div>
              <div className="fl">No. pedido</div>
              <div className="fv mono">{oGuion(selected.numero_pedido)}</div>
            </div>
          </div>
          <div className="fl">Referencia adicional</div>
          <div className="fv">{oGuion(selected.referencia_adicional)}</div>

          <div className="sec">
            Receptor <FieldTag origin="heredado" />
          </div>
          <div className="fl">Razón social facturación</div>
          <div className="fv">{selected.razon_social_facturacion}</div>
          <div className="r2">
            <div>
              <div className="fl">RFC</div>
              <div className="fv mono">{selected.rfc_facturacion}</div>
            </div>
            <div>
              <div className="fl">Dirección</div>
              <div className="fv" style={{ fontSize: 12 }}>
                {oGuion(selected.direccion_facturacion)}
              </div>
            </div>
          </div>

          <div className="sec">Concepto</div>
          <div className="fl">Descripción</div>
          <div className="fv muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
            {selected.descripcion_factura}
          </div>
          {selected.observaciones_factura && (
            <>
              <div className="fl">Observaciones</div>
              <div className="fv muted">{selected.observaciones_factura}</div>
            </>
          )}

          <div className="sec">
            Período de transmisión <FieldTag origin="heredado" />
          </div>
          <div className="r2">
            <div>
              <div className="fl">Inicio</div>
              <div className="fv mono">{fmtFecha(selected.fecha_inicio_transmision)}</div>
            </div>
            <div>
              <div className="fl">Fin</div>
              <div className="fv mono">{fmtFecha(selected.fecha_fin_transmision)}</div>
            </div>
          </div>

          <div className="sec">Configuración contable</div>
          <div className="fl">Método de pago</div>
          <div className="fv mono">{selected.metodo_pago_clave}</div>
          <div className="fl">Información cuenta de pago</div>
          <div className="fv muted" style={{ fontSize: 12 }}>
            {oGuion(selected.info_cuenta_pago)}
          </div>

          <div className="sec">Fechas</div>
          <div className="r2">
            <div>
              <div className="fl">Fecha factura</div>
              <div className="fv mono">{fmtFecha(selected.fecha_factura)}</div>
            </div>
            <div>
              <div className="fl">Fecha entrega</div>
              <div className="fv mono">{fmtFecha(selected.fecha_entrega_factura)}</div>
            </div>
          </div>

          {timbrada && (
            <>
              <div className="sec">
                Datos del timbrado <FieldTag origin="timbrado" />
              </div>
              <div className="fl">Folio fiscal SAT (UUID)</div>
              <div
                className="fv mono"
                style={{
                  fontSize: 11,
                  background: "var(--purple-bg)",
                  padding: "6px 8px",
                  borderRadius: 6,
                  display: "inline-block",
                }}
              >
                {oGuion(selected.folio_fiscal_sat)}
              </div>
              <div className="r2">
                <div>
                  <div className="fl">Fecha timbrado</div>
                  <div className="fv mono">{fmtFecha(selected.fecha_timbrado)}</div>
                </div>
                <div>
                  <div className="fl">Serie / certificado</div>
                  <div className="fv mono">{oGuion(selected.serie_timbrado)}</div>
                </div>
              </div>
            </>
          )}

          {estado === "preparada" && (
            <div className="state-msg" style={{ textAlign: "left" }}>
              <strong>Lista para enviar a timbrado.</strong> Descarga el archivo plano,
              envíalo al timbrador externo y regresa a registrar el folio fiscal.
            </div>
          )}
          {estado === "enviada_a_timbrado" && (
            <div className="state-msg" style={{ textAlign: "left" }}>
              <strong>Esperando respuesta del timbrado.</strong> Cuando la recibas, captura el
              folio fiscal.
            </div>
          )}
        </div>

        <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
          {errorAccion && (
            <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
          {faltantes !== null &&
            (faltantes.length === 0 ? (
              <div className="state-msg" style={{ margin: 0, textAlign: "left" }}>
                Archivo generado y completo.
              </div>
            ) : (
              <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
                <strong>Archivo generado, pero INCOMPLETO.</strong> El PAC lo rechazaría:
                faltan {faltantes.length} campos que el sistema todavía no captura (
                {faltantes.join(", ")}).
              </div>
            ))}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => descargarArchivo(selected)}
              title="Genera el archivo en el layout del PAC (V40)"
            >
              <i className="pi pi-download" aria-hidden="true" /> Archivo plano
            </button>
            {estado === "preparada" && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={enviarATimbrado.isPending}
                onClick={() => ejecutar(() => enviarATimbrado.mutateAsync(selected.factura_id))}
              >
                Marcar enviada a timbrado →
              </button>
            )}
            {estado === "enviada_a_timbrado" && (
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => {
                  setErrorAccion(null);
                  setModo("timbrar");
                }}
              >
                Registrar respuesta del timbrado →
              </button>
            )}
            {estado === "timbrada" && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={entregar.isPending}
                onClick={() => ejecutar(() => entregar.mutateAsync({ id: selected.factura_id }))}
              >
                Marcar entregada →
              </button>
            )}
            {estado === "entregada" && (
              <button type="button" className="btn btn-sm btn-dark" disabled>
                Pasa a CxC (Fase 3)
              </button>
            )}
            {["preparada", "enviada_a_timbrado", "timbrada", "entregada"].includes(estado) && (
              <button
                type="button"
                className="btn btn-sm btn-danger"
                disabled={cancelar.isPending}
                title={
                  ["timbrada", "entregada"].includes(estado)
                    ? "La orden asociada regresará a «orden cerrada» y podrá volver a facturarse."
                    : undefined
                }
                onClick={() => ejecutar(() => cancelar.mutateAsync(selected.factura_id))}
              >
                Cancelar
              </button>
            )}
          </div>
        </div>
      </>
    );
  } else {
    detail = (
      <DetailEmpty message="Selecciona una factura para ver el detalle o generar el envío a timbrado." />
    );
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = (list.data?.items ?? []).filter((f) =>
    filtro === "pendientes_timbrar"
      ? ["preparada", "enviada_a_timbrado"].includes(f.estado_facturacion)
      : true,
  );
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: "11%" }}>No. factura</th>
            <th style={{ width: "11%" }}>Pedido</th>
            <th style={{ width: "18%" }}>Razón social receptor</th>
            <th style={{ width: "12%" }}>Empresa emisora</th>
            <th style={{ width: "11%" }}>Fecha</th>
            <th style={{ width: "11%" }} className="td-right">
              Total
            </th>
            <th style={{ width: "14%" }}>Folio fiscal</th>
            <th style={{ width: "12%" }} className="td-center">
              Estado
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr
              key={f.factura_id}
              className={selected?.factura_id === f.factura_id ? "sel" : ""}
              onClick={() => seleccionar(f)}
            >
              <td className="td-main mono">{f.numero_factura}</td>
              <td className="td-2 mono" style={{ fontSize: 11 }}>
                {oGuion(f.numero_pedido)}
              </td>
              <td className="td-2">{f.razon_social_facturacion}</td>
              <td className="td-2" style={{ fontSize: 12 }}>
                {oGuion(f.empresa_facturadora)}
              </td>
              <td className="td-2 mono" style={{ fontSize: 11 }}>
                {fmtFecha(f.fecha_factura)}
              </td>
              <td className="td-2 td-right mono">{fmtMoneda(f.total_factura)}</td>
              <td className="td-2 mono" style={{ fontSize: 10 }}>
                {f.folio_fiscal_sat ? (
                  `${f.folio_fiscal_sat.slice(0, 13)}…`
                ) : (
                  <span style={{ color: "var(--amber-text)" }}>— sin timbrar —</span>
                )}
              </td>
              <td className="td-center">
                <span className={`badge ${badgeEstadoFactura(f.estado_facturacion)}`}>
                  {ESTADO_FACTURACION_LABEL[f.estado_facturacion]}
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
          <div className="cat-title">Facturas al cliente</div>
          <div className="cat-sub">
            El sistema <strong>prepara</strong> toda la información necesaria para enviar al
            sistema externo de timbrado. NO timbra internamente. Al recibir respuesta del
            timbrado, se registran folio fiscal, XML y PDF.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!hayOrdenesPorFacturar}
          title={
            hayOrdenesPorFacturar
              ? undefined
              : "No hay órdenes cerradas pendientes de facturar."
          }
          onClick={onIrAListasParaFacturar}
        >
          + Generar factura desde orden cerrada
        </button>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar número, pedido, razón social…"
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
