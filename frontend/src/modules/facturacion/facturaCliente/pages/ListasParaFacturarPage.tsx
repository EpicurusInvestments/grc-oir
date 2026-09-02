/** Bandeja "Listas para facturar" (pantalla aprobada `Fase_2_-_Facturacion.html`).
 *
 * Órdenes en `orden_cerrada` que todavía NO tienen factura vigente. Es el atajo operativo
 * del día a día de Facturación: qué falta por facturar, sin ir a rebuscar en la bandeja de
 * F1.
 *
 * Malla de tarjetas y no tabla, como el mockup: cada renglón es una decisión ("¿facturo
 * esta?"), no un dato que se compare en columnas, y la tarjeta deja ver de un vistazo
 * anunciante, agencia, campaña y total.
 *
 * Tiene DOS modos. El normal factura una orden por tarjeta. El **múltiple** (ADR-064)
 * agrupa varias órdenes de un mismo anunciante en una sola factura: se elige el anunciante
 * en un combo, se marcan las órdenes y se genera una factura con la suma. La tarjeta es la
 * misma en los dos modos —solo cambia su acción— para que el usuario no tenga que releer
 * una pantalla distinta.
 *
 * El alta REUTILIZA `FacturaClienteForm` con las órdenes ya fijadas — no hay un segundo
 * formulario que mantener en paralelo.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { Paginator, SearchableSelect } from "@/shared/ui";

import { FacturaClienteForm } from "../components/FacturaClienteForm";
import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import {
  useAnunciantesFacturables,
  useFacturasCliente,
  useOrdenesPorFacturar,
} from "../../hooks";
import type { FacturaClienteCreate, OrdenPorFacturar } from "../../types";

/** Mínimo de órdenes para que una factura múltiple tenga sentido. Es también el `minimo`
 *  con el que el backend arma el combo, así que los dos criterios coinciden. */
const MINIMO_MULTIPLE = 2;

export function ListasParaFacturarPage() {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [orden, setOrden] = useState<OrdenPorFacturar | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [creada, setCreada] = useState<string | null>(null);

  // ── modo múltiple ──
  const [multiple, setMultiple] = useState(false);
  const [anuncianteId, setAnuncianteId] = useState("");
  const [marcadas, setMarcadas] = useState<string[]>([]);
  const [errorSeleccion, setErrorSeleccion] = useState<string | null>(null);
  const [ordenesMultiples, setOrdenesMultiples] = useState<OrdenPorFacturar[] | null>(null);

  const qc = useQueryClient();
  // En modo múltiple la bandeja se acota al anunciante elegido; mientras no se elija
  // ninguno no se pide nada, porque la pantalla muestra la invitación a elegirlo.
  const lista = useOrdenesPorFacturar({
    page,
    size,
    anunciante_id: multiple ? anuncianteId || undefined : undefined,
  });
  const anunciantes = useAnunciantesFacturables(multiple);
  // Se reutiliza la mutación de alta del módulo: misma validación, mismos errores.
  const { crear } = useFacturasCliente({ page: 1, size: 1 });

  const items = lista.data?.items ?? [];
  const seleccionadas = items.filter((o) => marcadas.includes(o.orden_id));
  const totalSeleccionado = seleccionadas.reduce((suma, o) => suma + Number(o.total), 0);

  const salirDeMultiple = () => {
    setMultiple(false);
    setAnuncianteId("");
    setMarcadas([]);
    setErrorSeleccion(null);
    setPage(1);
  };

  const alternarMarcada = (ordenId: string) => {
    setErrorSeleccion(null);
    setMarcadas((previas) =>
      previas.includes(ordenId)
        ? previas.filter((id) => id !== ordenId)
        : [...previas, ordenId],
    );
  };

  const onCrear = async (data: FacturaClienteCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      // Las órdenes dejan de estar pendientes: esta bandeja tiene su propia clave de caché
      // y la mutación no la conoce, así que se invalida aquí explícitamente.
      qc.invalidateQueries({ queryKey: ["facturacion:por-facturar"] });
      setCreada(nueva.numero_factura);
      setOrden(null);
      setOrdenesMultiples(null);
      setMarcadas([]);
    } catch (e) {
      setSubmitError(
        e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.",
      );
    }
  };

  /** Valida al HACER CLIC, no deshabilitando el botón: si la acción no se puede hacer
   *  todavía, el usuario merece saber por qué y no un botón muerto sin explicación. */
  const generarMultiple = () => {
    if (seleccionadas.length < MINIMO_MULTIPLE) {
      setErrorSeleccion(
        `Selecciona al menos ${MINIMO_MULTIPLE} órdenes para generar una factura múltiple. ` +
          `Llevas ${seleccionadas.length}.`,
      );
      return;
    }
    setErrorSeleccion(null);
    setCreada(null);
    setSubmitError(null);
    setOrdenesMultiples(seleccionadas);
  };

  // ── Formulario de alta (una orden o varias) ─────────────────────────────────
  const enFormulario = orden ?? ordenesMultiples?.[0] ?? null;
  if (enFormulario) {
    const varias = ordenesMultiples ?? null;
    const titulo = varias
      ? `Nueva factura múltiple · ${varias.length} órdenes`
      : `Nueva factura · ${enFormulario.folio_orden}`;
    return (
      <>
        <div className="cat-header">
          <div>
            <div className="cat-title">{titulo}</div>
            <div className="cat-sub">
              {enFormulario.anunciante} ·{" "}
              {oGuion(enFormulario.agencia) === "—" ? "Trato directo" : enFormulario.agencia}
              {varias && (
                <>
                  {" · "}
                  <span className="mono">{varias.map((o) => o.folio_orden).join(", ")}</span>
                </>
              )}
            </div>
          </div>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setOrden(null);
              setOrdenesMultiples(null);
            }}
          >
            ← Volver a la bandeja
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
          <FacturaClienteForm
            orden={enFormulario}
            ordenes={varias ?? undefined}
            submitting={crear.isPending}
            submitError={submitError}
            onSubmit={onCrear}
            onCancel={() => {
              setOrden(null);
              setOrdenesMultiples(null);
            }}
          />
        </div>
      </>
    );
  }

  // ── Bandeja ─────────────────────────────────────────────────────────────────
  const esperandoAnunciante = multiple && !anuncianteId;

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Órdenes listas para facturar</div>
          <div className="cat-sub">
            Órdenes en estado <strong>orden cerrada</strong> que aún no tienen factura
            generada.{" "}
            {multiple
              ? "Elige un anunciante y marca las órdenes que irán en la misma factura."
              : "Selecciona una para empezar a prepararla."}
          </div>
        </div>
      </div>

      {/* Tarjeta del modo múltiple: mismo look que las secciones de "Nueva orden del
          cliente" (`.form-card` + `.check-box`), en vez de la barra plana anterior. Vive
          fuera del scroll de las tarjetas para que siga visible al marcar órdenes en una
          lista larga. */}
      <div style={{ padding: "16px 22px 0" }}>
        <div className="form-card" style={{ marginBottom: 0 }}>
          <div className="form-card-title">Facturación múltiple</div>
          <label className="check-box" style={{ marginBottom: multiple ? 16 : 0 }}>
            <input
              type="checkbox"
              checked={multiple}
              onChange={(e) => (e.target.checked ? setMultiple(true) : salirDeMultiple())}
            />
            <div>
              <div className="check-box-title">Facturar Múltiples Órdenes</div>
              <div className="check-box-desc">
                Agrupa varias órdenes cerradas del mismo anunciante en una sola factura.
              </div>
            </div>
          </label>

          {multiple && (
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div className="fl" style={{ width: "100%", marginBottom: -6 }}>
                Anunciante
              </div>
              <div className="combo-anunciante">
                <SearchableSelect
                  value={anuncianteId}
                  onChange={(v) => {
                    setAnuncianteId(v);
                    setMarcadas([]);
                    setErrorSeleccion(null);
                    setPage(1);
                  }}
                  options={(anunciantes.data ?? []).map((a) => ({
                    value: a.anunciante_id,
                    label: `${a.anunciante} · ${a.ordenes} órdenes`,
                  }))}
                  placeholder="Seleccionar Anunciante"
                  emptyOptionLabel="Seleccionar Anunciante"
                  emptyResultsLabel="Ningún anunciante coincide"
                />
              </div>

              <button type="button" className="btn btn-primary" onClick={generarMultiple}>
                Generar Factura Múltiple
              </button>

              {seleccionadas.length > 0 && (
                <span className="resumen-multiple">
                  {seleccionadas.length} seleccionadas ·{" "}
                  <span className="mono">{fmtMoneda(String(totalSeleccionado))}</span>
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {multiple && anunciantes.isSuccess && anunciantes.data.length === 0 && (
        <div className="state-msg" style={{ textAlign: "left" }}>
          Ningún anunciante tiene {MINIMO_MULTIPLE} o más órdenes disponibles, así que no hay
          nada que agrupar todavía.
        </div>
      )}

      {errorSeleccion && (
        <div className="state-msg error" style={{ textAlign: "left" }}>
          {errorSeleccion}
        </div>
      )}

      {creada && (
        <div className="state-msg" style={{ textAlign: "left" }}>
          Factura <strong>{creada}</strong> creada. Ya aparece en «Facturas al cliente».
        </div>
      )}

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        {esperandoAnunciante && (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text3)" }}>
            <div style={{ fontSize: 14, marginBottom: 8 }}>
              Elige un anunciante para ver sus órdenes cerradas
            </div>
            <div style={{ fontSize: 12 }}>
              El combo solo lista anunciantes con {MINIMO_MULTIPLE} o más órdenes por
              facturar.
            </div>
          </div>
        )}

        {!esperandoAnunciante && lista.isLoading && (
          <div className="state-msg">Cargando órdenes…</div>
        )}
        {!esperandoAnunciante && lista.isError && (
          <div className="state-msg error">No se pudieron cargar las órdenes.</div>
        )}

        {!esperandoAnunciante && !lista.isLoading && !lista.isError && items.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text3)" }}>
            <div style={{ fontSize: 14, marginBottom: 8 }}>
              ✓ No hay órdenes pendientes de facturar
            </div>
            <div style={{ fontSize: 12 }}>
              Todas las órdenes cerradas ya tienen factura generada.
            </div>
          </div>
        )}

        {!esperandoAnunciante && items.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
              gap: 14,
              maxWidth: 1400,
              margin: "0 auto",
            }}
          >
            {items.map((o) => {
              const marcada = marcadas.includes(o.orden_id);
              return (
                <div
                  key={o.orden_id}
                  className={`card-por-facturar${marcada ? " marcada" : ""}`}
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
                    style={{
                      display: "flex",
                      alignItems: "flex-end",
                      justifyContent: "space-between",
                    }}
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

                    {multiple ? (
                      <label className="check-incluir">
                        <input
                          type="checkbox"
                          checked={marcada}
                          onChange={() => alternarMarcada(o.orden_id)}
                        />
                        <span>Incluir en la factura</span>
                      </label>
                    ) : (
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
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!esperandoAnunciante && lista.data && lista.data.total > size && (
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
