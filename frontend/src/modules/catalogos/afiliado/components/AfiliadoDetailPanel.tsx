/** Panel de detalle del Afiliado: datos fiscales + contacto legado + Contactos ANIDADOS
 * (add/edit/desactivar inline, ADR-094) + Estaciones (lectura, ver abajo).
 *
 * "Contacto" (`contacto_nombre`/`contacto_email`/`contacto_telefono`) es el único
 * contacto plano de la spec original — queda como LEGADO, de solo lectura (ya no se
 * captura desde el formulario). "Contactos" es la lista nueva (varios), entidad fuera
 * de la spec BD v2, mismo patrón anidado que `ContactoAnunciante`/`ContactoAgencia`.
 *
 * Las Estaciones YA NO se administran aquí (ADR-094: pantalla propia,
 * `modules/catalogos/estacion/`) — esta sección es de SOLO LECTURA, para no tener dos
 * formas de hacer lo mismo. Alta/edición/baja de estaciones vive en su pantalla.
 */

import { useEstacionesPorAfiliado } from "@/modules/catalogos/estacion/hooks";
import type { TipoSenal } from "@/modules/catalogos/estacion/types";
import { FieldTag, StatusBadge } from "@/shared/ui";

import type { Afiliado } from "../types";
import { ContactosSection } from "./ContactosSection";

const TIPO_BADGE: Record<TipoSenal, string> = { fm: "b-teal", am: "b-amber", tv: "b-blue" };

interface AfiliadoDetailPanelProps {
  afiliado: Afiliado;
  canWrite: boolean;
  onEdit: () => void;
  onToggleActivo: () => void;
  togglingActivo?: boolean;
}

export function AfiliadoDetailPanel({
  afiliado,
  canWrite,
  onEdit,
  onToggleActivo,
  togglingActivo,
}: AfiliadoDetailPanelProps) {
  const estaciones = useEstacionesPorAfiliado(afiliado.afiliado_id);
  const estacionItems = estaciones.data?.items ?? [];

  return (
    <>
      <div className="dh">
        <div className="dh-row">
          <div>
            <div className="dh-name">{afiliado.nombre_afiliado}</div>
            <div className="dh-sub">
              <StatusBadge activo={afiliado.activo} />
              <span className="badge b-blue">{estacionItems.length} estaciones</span>
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

        {(afiliado.contacto_nombre || afiliado.contacto_email || afiliado.contacto_telefono) && (
          <>
            <div className="sec">
              Contacto <FieldTag origin="derivado" text="Legado" />
            </div>
            <div className="fl">Nombre</div>
            <div className="fv">{afiliado.contacto_nombre ?? "—"}</div>
            <div className="fl">Correo</div>
            <div className="fv link">{afiliado.contacto_email ?? "—"}</div>
            <div className="fl">Teléfono</div>
            <div className="fv">{afiliado.contacto_telefono ?? "—"}</div>
          </>
        )}

        {/* ── Contactos anidados (entidad nueva, reemplaza al contacto único de arriba) ── */}
        <ContactosSection
          afiliadoId={afiliado.afiliado_id}
          canWrite={canWrite}
          contactosNuevos={[]}
          onContactosNuevosChange={() => {}}
        />

        {/* ── Estaciones (solo lectura — gestión completa en la pantalla propia) ── */}
        <div className="sec">Estaciones ({estacionItems.length})</div>
        {estaciones.isLoading && <div className="state-msg">Cargando estaciones…</div>}
        {estaciones.isError && (
          <div className="state-msg error">No se pudieron cargar las estaciones.</div>
        )}
        {!estaciones.isLoading && estacionItems.length === 0 && (
          <div className="fv muted">Sin estaciones registradas.</div>
        )}
        {estacionItems.map((e) => (
          <div className="rel-item" key={e.estacion_id}>
            <div>
              <div className="rel-name">{e.nombre_estacion}</div>
              <div className="rel-sub">
                {e.frecuencia ?? "—"} · {e.plaza_nombre ?? "—"}
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span className={`badge ${TIPO_BADGE[e.tipo_senal]}`}>
                {e.tipo_senal.toUpperCase()}
              </span>
              <StatusBadge activo={e.activo} labelActivo="Act" labelInactivo="Inact" />
            </div>
          </div>
        ))}
        {estacionItems.length > 0 && (
          <div className="fv muted" style={{ fontSize: 11, marginTop: -4 }}>
            Alta, edición y baja de estaciones: pantalla "Estaciones".
          </div>
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
