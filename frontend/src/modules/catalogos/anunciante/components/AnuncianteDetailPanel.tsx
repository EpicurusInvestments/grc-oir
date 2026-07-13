/** Panel de detalle del Anunciante: identificación fiscal + contacto + condiciones
 * (días de crédito, sensible) + Marcas ANIDADAS (add/edit/desactivar inline, patrón
 * Estación-en-Afiliado) + Contratos (lectura) + Historial de cambios.
 */

import { useState } from "react";

import { FieldTag, StatusBadge } from "@/shared/ui";

import { useContratosPorAnunciante, useHistorialAnunciante, useMarcas } from "../hooks";
import type { Anunciante, AnuncianteContrato, Marca } from "../types";
import { MarcaInlineForm, type MarcaFormData } from "./MarcaInlineForm";

const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

const fmtFechaHora = (iso: string): string =>
  new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });

const fmtMonto = (v: string | null): string =>
  v == null
    ? "—"
    : Number(v).toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });

const ESTADO_BADGE: Record<AnuncianteContrato["estado_contrato"], string> = {
  vigente: "b-green",
  suspendido: "b-amber",
  finalizado: "b-gray",
  cancelado: "b-red",
};

const CAMPO_LABEL: Record<string, string> = { dias_credito_default: "Días de crédito" };
const labelCampo = (c: string) => CAMPO_LABEL[c] ?? c;

interface AnuncianteDetailPanelProps {
  anunciante: Anunciante;
  canWrite: boolean;
  onEdit: () => void;
  onToggleActivo: () => void;
  togglingActivo?: boolean;
}

export function AnuncianteDetailPanel({
  anunciante,
  canWrite,
  onEdit,
  onToggleActivo,
  togglingActivo,
}: AnuncianteDetailPanelProps) {
  const { useListPorAnunciante, useCreate, useUpdate, useSetEstado } = useMarcas();
  const marcas = useListPorAnunciante(anunciante.anunciante_id, { size: 100 });
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  const contratos = useContratosPorAnunciante(anunciante.anunciante_id);
  const historial = useHistorialAnunciante(anunciante.anunciante_id);

  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Marca | null>(null);

  const marcaItems = marcas.data?.items ?? [];
  const contratoItems = contratos.data?.items ?? [];
  const histItems = historial.data ?? [];

  const cerrarForm = () => {
    setAdding(false);
    setEditing(null);
  };

  const onCrearMarca = async (data: MarcaFormData) => {
    await crear.mutateAsync({ anunciante_id: anunciante.anunciante_id, ...data });
    cerrarForm();
  };

  const onActualizarMarca = async (data: MarcaFormData) => {
    if (!editing) return;
    await actualizar.mutateAsync({ id: editing.marca_id, data });
    cerrarForm();
  };

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{anunciante.nombre_comercial}</div>
            <div className="dh-sub">
              <StatusBadge activo={anunciante.activo} />
              {anunciante.agencia_id ? (
                <span className="badge b-teal">Vía {anunciante.agencia_nombre}</span>
              ) : (
                <span className="badge b-purple">Sin agencia</span>
              )}
            </div>
          </div>
          {canWrite && (
            <button type="button" className="btn btn-sm" onClick={onEdit}>
              Editar
            </button>
          )}
        </div>
      </div>

      <div className="db">
        <div className="sec">Identificación fiscal</div>
        <div className="fl">Nombre fiscal / Razón social</div>
        <div className="fv">{anunciante.nombre_fiscal}</div>
        <div className="fl">RFC</div>
        <div className="fv mono">{anunciante.rfc_anunciante}</div>
        <div className="fl">Localización</div>
        <div className="fv">{oGuion(anunciante.localizacion)}</div>
        <div className="fl">Referencia interna</div>
        <div className="fv mono">{oGuion(anunciante.referencia_anunciante)}</div>

        <div className="sec">Contacto comercial</div>
        <div className="fl">Nombre</div>
        <div className="fv">{oGuion(anunciante.contacto_nombre)}</div>
        <div className="fl">Correo</div>
        <div className="fv link">{oGuion(anunciante.contacto_email)}</div>
        <div className="fl">Teléfono</div>
        <div className="fv">{oGuion(anunciante.contacto_telefono)}</div>

        <div className="sec">Condiciones default</div>
        <div className="fl">
          Días de crédito (default) <FieldTag origin="audit" />
        </div>
        <div className="fv mono">{anunciante.dias_credito_default} días</div>
        <div className="fv muted" style={{ marginTop: -6, fontSize: 11 }}>
          Valor sugerido al crear cobranzas. Puede sobreescribirse por factura.
        </div>

        {/* ── Marcas anidadas ── */}
        <div className="sec">
          <span>Marcas ({marcaItems.length})</span>
          {canWrite && !adding && !editing && (
            <button type="button" className="btn btn-xs" onClick={() => setAdding(true)}>
              + Agregar
            </button>
          )}
        </div>

        {adding && (
          <MarcaInlineForm
            title="Nueva marca"
            submitting={crear.isPending}
            onSubmit={onCrearMarca}
            onCancel={cerrarForm}
          />
        )}

        {marcas.isLoading && <div className="state-msg">Cargando marcas…</div>}
        {marcas.isError && <div className="state-msg error">No se pudieron cargar las marcas.</div>}
        {!marcas.isLoading && marcaItems.length === 0 && !adding && (
          <div className="fv muted">Sin marcas registradas.</div>
        )}

        {marcaItems.map((m) =>
          editing?.marca_id === m.marca_id ? (
            <MarcaInlineForm
              key={m.marca_id}
              title="Editar marca"
              defaultValues={{ nombre_marca: m.nombre_marca }}
              submitting={actualizar.isPending}
              onSubmit={onActualizarMarca}
              onCancel={cerrarForm}
            />
          ) : (
            <div className="rel-item" key={m.marca_id}>
              <div>
                <div className="rel-name">{m.nombre_marca}</div>
                <div className="rel-sub">Marca asociada</div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <StatusBadge activo={m.activo} labelActivo="Act" labelInactivo="Inact" />
                {canWrite && (
                  <>
                    <button type="button" className="btn btn-xs" onClick={() => setEditing(m)}>
                      Editar
                    </button>
                    <button
                      type="button"
                      className={`btn btn-xs ${m.activo ? "btn-danger" : ""}`}
                      disabled={setEstado.isPending}
                      onClick={() => setEstado.mutateAsync({ id: m.marca_id, activo: !m.activo })}
                    >
                      {m.activo ? "Desactivar" : "Activar"}
                    </button>
                  </>
                )}
              </div>
            </div>
          ),
        )}

        {/* ── Contratos (lectura; la pantalla de Contrato llega en la Tanda 6) ── */}
        <div className="sec">Contratos ({contratoItems.length})</div>
        {contratos.isLoading && <div className="state-msg">Cargando contratos…</div>}
        {contratos.isError && (
          <div className="state-msg error">No se pudieron cargar los contratos.</div>
        )}
        {!contratos.isLoading && !contratos.isError && contratoItems.length === 0 && (
          <div className="fv muted">Sin contratos registrados.</div>
        )}
        {contratoItems.map((c) => (
          <div className="rel-item" key={c.contrato_id}>
            <div>
              <div className="rel-name">{c.nombre_contrato}</div>
              <div className="rel-sub">
                {c.numero_contrato} · {c.fecha_inicio_contrato} a {c.fecha_fin_contrato} ·{" "}
                {fmtMonto(c.monto_contrato)}
              </div>
            </div>
            <span className={`badge ${ESTADO_BADGE[c.estado_contrato]}`}>{c.estado_contrato}</span>
          </div>
        ))}

        {/* ── Historial de cambios (auditoría del anunciante) ── */}
        <div className="sec">Historial de cambios</div>
        {historial.isLoading && <div className="state-msg">Cargando historial…</div>}
        {historial.isError && <div className="state-msg error">No se pudo cargar el historial.</div>}
        {!historial.isLoading && !historial.isError && histItems.length === 0 && (
          <div className="fv muted">Sin cambios registrados.</div>
        )}
        {histItems.map((h) => (
          <div className="rel-item" key={h.log_cambio_parametro_id}>
            <div>
              <div className="rel-name">
                {labelCampo(h.campo)}: <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_anterior)}</span>{" "}
                → <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_nuevo)}</span>
              </div>
              <div className="rel-sub">
                {fmtFechaHora(h.fecha_cambio)} · {h.usuario}
                {h.motivo_cambio ? ` · ${h.motivo_cambio}` : ""}
              </div>
            </div>
          </div>
        ))}
      </div>

      {canWrite && (
        <div className="df">
          <button
            type="button"
            className={`btn btn-sm ${anunciante.activo ? "btn-danger" : ""}`}
            disabled={togglingActivo}
            onClick={onToggleActivo}
          >
            {anunciante.activo ? "Desactivar anunciante" : "Activar anunciante"}
          </button>
        </div>
      )}
    </>
  );
}
