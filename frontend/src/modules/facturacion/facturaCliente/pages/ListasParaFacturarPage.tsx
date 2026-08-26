/** Bandeja "Listas para facturar" (pantalla aprobada `Fase_2_-_Facturacion.html`).
 *
 * Órdenes en `orden_cerrada` que todavía NO tienen factura. Es el atajo operativo del día
 * a día de Facturación: qué falta por facturar, sin ir a rebuscar en la bandeja de F1.
 *
 * Malla de tarjetas y no tabla, como el mockup: cada renglón es una decisión ("¿facturo
 * esta?"), no un dato que se compare en columnas, y la tarjeta deja ver de un vistazo
 * anunciante, agencia, campaña y total.
 *
 * El alta REUTILIZA `FacturaClienteForm` con la orden ya fijada — no hay un segundo
 * formulario que mantener en paralelo.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { Paginator } from "@/shared/ui";

import { FacturaClienteForm } from "../components/FacturaClienteForm";
import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useFacturasCliente, useOrdenesPorFacturar } from "../../hooks";
import type { FacturaClienteCreate, OrdenPorFacturar } from "../../types";

export function ListasParaFacturarPage() {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [orden, setOrden] = useState<OrdenPorFacturar | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [creada, setCreada] = useState<string | null>(null);

  const qc = useQueryClient();
  const lista = useOrdenesPorFacturar({ page, size });
  // Se reutiliza la mutación de alta del módulo: misma validación, mismos errores.
  const { crear } = useFacturasCliente({ page: 1, size: 1 });

  const onCrear = async (data: FacturaClienteCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      // La orden deja de estar pendiente: esta bandeja tiene su propia clave de caché y
      // la mutación no la conoce, así que se invalida aquí explícitamente.
      qc.invalidateQueries({ queryKey: ["facturacion:por-facturar"] });
      setCreada(nueva.numero_factura);
      setOrden(null);
    } catch (e) {
      setSubmitError(
        e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.",
      );
    }
  };

  if (orden) {
    return (
      <>
        <div className="cat-header">
          <div>
            <div className="cat-title">Nueva factura · {orden.folio_orden}</div>
            <div className="cat-sub">
              {orden.anunciante} · {oGuion(orden.agencia) === "—" ? "Trato directo" : orden.agencia}
            </div>
          </div>
          <button type="button" className="btn" onClick={() => setOrden(null)}>
            ← Volver a la bandeja
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
          <FacturaClienteForm
            orden={orden}
            submitting={crear.isPending}
            submitError={submitError}
            onSubmit={onCrear}
            onCancel={() => setOrden(null)}
          />
        </div>
      </>
    );
  }

  const items = lista.data?.items ?? [];

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Órdenes listas para facturar</div>
          <div className="cat-sub">
            Órdenes en estado <strong>orden cerrada</strong> que aún no tienen factura
            generada. Selecciona una para empezar a prepararla.
          </div>
        </div>
      </div>

      {creada && (
        <div className="state-msg" style={{ textAlign: "left" }}>
          Factura <strong>{creada}</strong> creada. Ya aparece en «Facturas al cliente».
        </div>
      )}

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        {lista.isLoading && <div className="state-msg">Cargando órdenes…</div>}
        {lista.isError && (
          <div className="state-msg error">No se pudieron cargar las órdenes.</div>
        )}

        {!lista.isLoading && !lista.isError && items.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text3)" }}>
            <div style={{ fontSize: 14, marginBottom: 8 }}>
              ✓ No hay órdenes pendientes de facturar
            </div>
            <div style={{ fontSize: 12 }}>
              Todas las órdenes cerradas ya tienen factura generada.
            </div>
          </div>
        )}

        {items.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
              gap: 14,
              maxWidth: 1400,
              margin: "0 auto",
            }}
          >
            {items.map((o) => (
              <div
                key={o.orden_id}
                className="card-por-facturar"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--rl)",
                  padding: 16,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 8,
                  }}
                >
                  <span className="mono" style={{ fontWeight: 600 }}>
                    {o.folio_orden}
                  </span>
                  <span className="badge b-teal">Orden cerrada</span>
                </div>

                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 3 }}>
                  {o.anunciante}
                </div>
                <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 11 }}>
                  {o.agencia ?? "Trato directo"}
                  {o.vendedor ? ` · ${o.vendedor}` : ""}
                </div>
                <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 11 }}>
                  {oGuion(o.producto)}
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 8,
                    fontSize: 11,
                    marginBottom: 13,
                  }}
                >
                  <div>
                    <span style={{ color: "var(--text3)" }}>Campaña:</span>
                    <br />
                    <span className="mono">
                      {fmtFecha(o.fecha_inicio_campania)} → {fmtFecha(o.fecha_fin_campania)}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: "var(--text3)" }}>Pedido:</span>
                    <br />
                    <span className="mono">{o.numero_orden_cliente}</span>
                  </div>
                </div>

                <div
                  style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--text3)",
                        textTransform: "uppercase",
                        letterSpacing: ".05em",
                      }}
                    >
                      Total c/IVA
                    </div>
                    <div
                      className="mono"
                      style={{ fontSize: 18, fontWeight: 600, color: "var(--blue-text)" }}
                    >
                      {fmtMoneda(o.total)}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={() => {
                      setOrden(o);
                      setCreada(null);
                      setSubmitError(null);
                    }}
                  >
                    Generar factura →
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {lista.data && lista.data.total > size && (
          <Paginator
            page={page}
            size={size}
            total={lista.data.total}
            onChange={(np, ns) => {
              setPage(np);
              setSize(ns);
            }}
          />
        )}
      </div>
    </>
  );
}
