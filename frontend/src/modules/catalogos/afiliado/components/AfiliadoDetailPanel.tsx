/** Panel de detalle del Afiliado: datos fiscales + contacto + estaciones ANIDADAS.
 *
 * Las estaciones se listan, agregan y editan aquí mismo (form inline). La plaza de cada
 * estación se hereda del afiliado (ADR-005), así que no se captura. La baja del afiliado
 * se delega a la pantalla (puede requerir confirmación por estaciones activas).
 */

import { useState } from "react";

import type { Plaza } from "@/modules/catalogos/plaza/types";
import { FieldTag, StatusBadge } from "@/shared/ui";

import { useEstaciones } from "../hooks";
import type { Afiliado, Estacion, TipoSenal } from "../types";
import { EstacionInlineForm, type EstacionFormData } from "./EstacionInlineForm";

const TIPO_BADGE: Record<TipoSenal, string> = { fm: "b-teal", am: "b-amber", tv: "b-blue" };

interface AfiliadoDetailPanelProps {
  afiliado: Afiliado;
  plazas: Plaza[];
  canWrite: boolean;
  onEdit: () => void;
  onToggleActivo: () => void;
  togglingActivo?: boolean;
}

export function AfiliadoDetailPanel({
  afiliado,
  plazas,
  canWrite,
  onEdit,
  onToggleActivo,
  togglingActivo,
}: AfiliadoDetailPanelProps) {
  const { useListPorAfiliado, useCreate, useUpdate, useSetEstado } = useEstaciones();
  const estaciones = useListPorAfiliado(afiliado.afiliado_id, { size: 100 });
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Estacion | null>(null);

  const plazaNombre = plazas.find((p) => p.plaza_id === afiliado.plaza_id)?.nombre_plaza ?? "—";
  const items = estaciones.data?.items ?? [];

  const cerrarForm = () => {
    setAdding(false);
    setEditing(null);
  };

  const onCrearEstacion = async (data: EstacionFormData) => {
    await crear.mutateAsync({ afiliado_id: afiliado.afiliado_id, ...data });
    cerrarForm();
  };

  const onActualizarEstacion = async (data: EstacionFormData) => {
    if (!editing) return;
    await actualizar.mutateAsync({ id: editing.estacion_id, data });
    cerrarForm();
  };

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{afiliado.nombre_afiliado}</div>
            <div className="dh-sub">
              <StatusBadge activo={afiliado.activo} />
              <span>{plazaNombre}</span>
              <span className="badge b-blue">{items.length} estaciones</span>
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
        <div className="sec">Datos fiscales</div>
        <div className="fl">Razón social</div>
        <div className="fv">{afiliado.razon_social_afiliado}</div>
        <div className="fl">RFC</div>
        <div className="fv mono">{afiliado.rfc_afiliado}</div>
        <div className="fl">
          Plaza <FieldTag origin="catalogo" />
        </div>
        <div className="fv">{plazaNombre}</div>

        <div className="sec">Contacto</div>
        <div className="fl">Nombre</div>
        <div className="fv">{afiliado.contacto_nombre ?? "—"}</div>
        <div className="fl">Correo</div>
        <div className="fv link">{afiliado.contacto_email ?? "—"}</div>
        <div className="fl">Teléfono</div>
        <div className="fv">{afiliado.contacto_telefono ?? "—"}</div>

        <div className="sec">
          <span>Estaciones ({items.length})</span>
          {canWrite && !adding && !editing && (
            <button type="button" className="btn btn-xs" onClick={() => setAdding(true)}>
              + Agregar
            </button>
          )}
        </div>

        {adding && (
          <EstacionInlineForm
            title="Nueva estación"
            plazaNombre={plazaNombre}
            razonSocial={afiliado.razon_social_afiliado}
            submitting={crear.isPending}
            onSubmit={onCrearEstacion}
            onCancel={cerrarForm}
          />
        )}

        {estaciones.isLoading && <div className="state-msg">Cargando estaciones…</div>}
        {estaciones.isError && (
          <div className="state-msg error">No se pudieron cargar las estaciones.</div>
        )}
        {!estaciones.isLoading && items.length === 0 && !adding && (
          <div className="fv muted">Sin estaciones registradas.</div>
        )}

        {items.map((e) =>
          editing?.estacion_id === e.estacion_id ? (
            <EstacionInlineForm
              key={e.estacion_id}
              title="Editar estación"
              plazaNombre={plazaNombre}
              razonSocial={afiliado.razon_social_afiliado}
              defaultValues={{
                nombre_estacion: e.nombre_estacion,
                frecuencia: e.frecuencia ?? "",
                tipo_senal: e.tipo_senal,
              }}
              submitting={actualizar.isPending}
              onSubmit={onActualizarEstacion}
              onCancel={cerrarForm}
            />
          ) : (
            <div className="rel-item" key={e.estacion_id}>
              <div>
                <div className="rel-name">{e.nombre_estacion}</div>
                <div className="rel-sub">
                  {e.frecuencia ?? "—"} · {plazaNombre}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span className={`badge ${TIPO_BADGE[e.tipo_senal]}`}>
                  {e.tipo_senal.toUpperCase()}
                </span>
                <StatusBadge activo={e.activo} labelActivo="Act" labelInactivo="Inact" />
                {canWrite && (
                  <>
                    <button type="button" className="btn btn-xs" onClick={() => setEditing(e)}>
                      Editar
                    </button>
                    <button
                      type="button"
                      className={`btn btn-xs ${e.activo ? "btn-danger" : ""}`}
                      disabled={setEstado.isPending}
                      onClick={() =>
                        setEstado.mutateAsync({ id: e.estacion_id, activo: !e.activo })
                      }
                    >
                      {e.activo ? "Desactivar" : "Activar"}
                    </button>
                  </>
                )}
              </div>
            </div>
          ),
        )}
      </div>

      {canWrite && (
        <div className="df">
          <button
            type="button"
            className={`btn btn-sm ${afiliado.activo ? "btn-danger" : ""}`}
            disabled={togglingActivo}
            onClick={onToggleActivo}
          >
            {afiliado.activo ? "Desactivar afiliado" : "Activar afiliado"}
          </button>
        </div>
      )}
    </>
  );
}
