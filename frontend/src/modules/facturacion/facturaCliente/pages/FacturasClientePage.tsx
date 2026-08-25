/** Facturas al cliente (F2) — lista + panel de detalle, patrón de F0/F1.
 *
 * Las acciones del panel son las transiciones de la máquina de estados del backend, y se
 * muestran SOLO cuando son válidas desde el estado actual: la UI no ofrece un botón que
 * el servidor va a rechazar con 409. Aun así el backend valida siempre — esto es UX.
 *
 * Timbrar es la acción con efecto colateral: promueve la `OrdenCliente` a `facturada`
 * (el handoff de F2). El diálogo lo dice explícitamente, porque desde esta pantalla no se
 * ve la orden que se está moviendo.
 *
 * Cancelar es su espejo (ADR-047): si la orden quedó en `facturada`, vuelve a
 * `orden_cerrada` y reaparece en «Listas para facturar». El botón lo advierte en su
 * tooltip, por el mismo motivo. Si la orden ya está `cobrada`, el backend rechaza la
 * cancelación con 400 y el mensaje se pinta tal cual.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import { FacturaClienteForm } from "../components/FacturaClienteForm";
import { TimbrarDialog } from "../components/TimbrarDialog";
import { facturaClienteApi } from "../../api";
import { badgeEstadoFactura, fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useFacturasCliente } from "../../hooks";
import {
  ESTADO_FACTURACION_LABEL,
  type EstadoFacturacion,
  type FacturaCliente,
  type FacturaClienteCreate,
  type TimbrarInput,
} from "../../types";

type Filtro = "todas" | EstadoFacturacion;
type Modo = "view" | "new";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "preparada", label: "Preparadas" },
  { key: "enviada_a_timbrado", label: "En timbrado" },
  { key: "timbrada", label: "Timbradas" },
  { key: "entregada", label: "Entregadas" },
  { key: "cobrada", label: "Cobradas" },
  { key: "cancelada", label: "Canceladas" },
];

export function FacturasClientePage() {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<FacturaCliente | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [dialogoTimbrar, setDialogoTimbrar] = useState(false);

  const filtros = {
    page,
    size,
    q: q || undefined,
    estado_facturacion: filtro === "todas" ? undefined : filtro,
  };
  const { list, crear, enviarATimbrado, timbrar, entregar, cancelar } = useFacturasCliente(filtros);

  const mensajeDeError = (e: unknown): string => {
    if (e instanceof ApiRequestError) return e.message;
    return "Ocurrió un error inesperado.";
  };

  const seleccionar = (f: FacturaCliente) => {
    setSelected(f);
    setModo("view");
    setErrorAccion(null);
  };

  const onCrear = async (data: FacturaClienteCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const ejecutar = async (accion: () => Promise<FacturaCliente>) => {
    setErrorAccion(null);
    try {
      setSelected(await accion());
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onTimbrar = async (data: TimbrarInput) => {
    if (!selected) return;
    setErrorAccion(null);
    try {
      setSelected(await timbrar.mutateAsync({ id: selected.factura_id, data }));
      setDialogoTimbrar(false);
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
      setDialogoTimbrar(false);
    }
  };

  // ── panel de detalle ────────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <FacturaClienteForm
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={() => {
          setModo("view");
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const estado = selected.estado_facturacion;
    const puedeEnviar = estado === "preparada";
    const puedeTimbrar = estado === "enviada_a_timbrado";
    const puedeEntregar = estado === "timbrada";
    const puedeCancelar = ["preparada", "enviada_a_timbrado", "timbrada", "entregada"].includes(
      estado,
    );

    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.numero_factura}</div>
              <div className="dh-sub">{selected.razon_social_facturacion}</div>
            </div>
            <span className={`badge ${badgeEstadoFactura(estado)}`}>
              {ESTADO_FACTURACION_LABEL[estado]}
            </span>
          </div>
        </div>

        <div className="dg">
          <div className="sec">Receptor</div>
          <div className="fl">Razón social</div>
          <div className="fv">{selected.razon_social_facturacion}</div>
          <div className="fl">RFC</div>
          <div className="fv mono">{selected.rfc_facturacion}</div>

          <div className="sec">Importes</div>
          <div className="fl">Subtotal</div>
          <div className="fv">{fmtMoneda(selected.subtotal_factura)}</div>
          <div className="fl">IVA</div>
          <div className="fv">{fmtMoneda(selected.iva_factura)}</div>
          <div className="fl">Total</div>
          <div className="fv strong">{fmtMoneda(selected.total_factura)}</div>

          <div className="sec">Periodo y fechas</div>
          <div className="fl">Transmisión</div>
          <div className="fv">
            {fmtFecha(selected.fecha_inicio_transmision)} — {fmtFecha(selected.fecha_fin_transmision)}
          </div>
          <div className="fl">Factura</div>
          <div className="fv">{fmtFecha(selected.fecha_factura)}</div>
          <div className="fl">Entrega</div>
          <div className="fv muted">{fmtFecha(selected.fecha_entrega_factura)}</div>

          <div className="sec">Timbrado</div>
          <div className="fl">Folio fiscal</div>
          <div className="fv mono">{oGuion(selected.folio_fiscal_sat)}</div>
          <div className="fl">Fecha de timbrado</div>
          <div className="fv muted">{fmtFecha(selected.fecha_timbrado)}</div>
          <div className="fl">Método de pago</div>
          <div className="fv mono">{selected.metodo_pago_clave}</div>
        </div>

        <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
          {errorAccion && (
            <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                facturaClienteApi.descargarArchivoPlano(
                  selected.factura_id,
                  selected.numero_factura,
                )
              }
              title="Formato BORRADOR — el layout real del PAC está pendiente de especificación"
            >
              <i className="pi pi-download" aria-hidden="true" /> Archivo plano (borrador)
            </button>
            {puedeEnviar && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={enviarATimbrado.isPending}
                onClick={() => ejecutar(() => enviarATimbrado.mutateAsync(selected.factura_id))}
              >
                Enviar a timbrado
              </button>
            )}
            {puedeTimbrar && (
              <button type="button" className="btn btn-sm" onClick={() => setDialogoTimbrar(true)}>
                Registrar timbrado
              </button>
            )}
            {puedeEntregar && (
              <button
                type="button"
                className="btn btn-sm"
                disabled={entregar.isPending}
                onClick={() => ejecutar(() => entregar.mutateAsync({ id: selected.factura_id }))}
              >
                Marcar entregada
              </button>
            )}
            {puedeCancelar && (
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
    detail = <DetailEmpty message="Selecciona una factura para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: "16%" }}>Factura</th>
            <th>Receptor</th>
            <th style={{ width: "18%" }} className="td-right">
              Total
            </th>
            <th className="td-center" style={{ width: 150 }}>
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
              <td className="td-2">{f.razon_social_facturacion}</td>
              <td className="td-2 td-right">{fmtMoneda(f.total_factura)}</td>
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
            Preparación de la factura a partir de una orden cerrada. El sistema no timbra:
            exporta al timbrador externo y registra el folio fiscal que devuelve.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setSelected(null);
            setModo("new");
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
        searchPlaceholder="Buscar por número, razón social o folio fiscal…"
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

      {selected && (
        <TimbrarDialog
          visible={dialogoTimbrar}
          numeroFactura={selected.numero_factura}
          submitting={timbrar.isPending}
          onConfirm={onTimbrar}
          onCancel={() => setDialogoTimbrar(false)}
        />
      )}
    </>
  );
}
