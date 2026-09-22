/** Sección "Contactos" anidada, reutilizable en alta, edición y detalle de la Agencia.
 * Mismo criterio dual-modo que `catalogos/anunciante/components/ContactosSection.tsx`:
 *
 * - **Edición/detalle** (`agenciaId` presente): cada alta/edición/baja pega DIRECTO al
 *   backend (`useContactosAgencia`).
 * - **Alta** (`agenciaId` es `null`, la agencia todavía no existe): los contactos se
 *   guardan en un arreglo EN MEMORIA (`contactosNuevos`/`onContactosNuevosChange`, estado
 *   del formulario padre) y se mandan al backend uno por uno justo después de crear la
 *   agencia (ver `AgenciaCatalogPage.onCrear`). Por eso aquí no hay "Desactivar": un
 *   contacto que nunca se guardó no tiene estado que desactivar, solo "Quitar".
 */

import { useState } from "react";

import { StatusBadge } from "@/shared/ui";

import { useContactosAgencia } from "../hooks";
import { ContactoInlineForm, type ContactoFormData } from "./ContactoInlineForm";

interface ContactosSectionProps {
  agenciaId: string | null;
  canWrite: boolean;
  contactosNuevos: ContactoFormData[];
  onContactosNuevosChange: (items: ContactoFormData[]) => void;
}

export function ContactosSection({
  agenciaId,
  canWrite,
  contactosNuevos,
  onContactosNuevosChange,
}: ContactosSectionProps) {
  const esAlta = agenciaId == null;

  const { useListPorAgencia, useCreate, useUpdate, useSetEstado } = useContactosAgencia();
  const contactosServidor = useListPorAgencia(agenciaId, { size: 100 });
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  const [adding, setAdding] = useState(false);
  const [editingServerId, setEditingServerId] = useState<string | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const itemsServidor = contactosServidor.data?.items ?? [];
  const editando = editingServerId != null || editingIndex != null;

  const cerrarForm = () => {
    setAdding(false);
    setEditingServerId(null);
    setEditingIndex(null);
  };

  const onCrear = async (data: ContactoFormData) => {
    if (esAlta) {
      onContactosNuevosChange([...contactosNuevos, data]);
    } else {
      await crear.mutateAsync({ agencia_id: agenciaId, ...data });
    }
    cerrarForm();
  };

  const onActualizar = async (data: ContactoFormData) => {
    if (esAlta && editingIndex != null) {
      const copia = [...contactosNuevos];
      copia[editingIndex] = data;
      onContactosNuevosChange(copia);
    } else if (editingServerId != null) {
      await actualizar.mutateAsync({ id: editingServerId, data });
    }
    cerrarForm();
  };

  const quitarLocal = (idx: number) => {
    onContactosNuevosChange(contactosNuevos.filter((_, i) => i !== idx));
  };

  const editandoDefaultValues = () => {
    if (editingIndex != null) {
      const c = contactosNuevos[editingIndex];
      return {
        nombre_contacto: c.nombre_contacto,
        puesto_contacto: c.puesto_contacto ?? "",
        telefono_contacto: c.telefono_contacto ?? "",
        email_contacto: c.email_contacto ?? "",
      };
    }
    const c = itemsServidor.find((c) => c.contacto_agencia_id === editingServerId);
    if (!c) return undefined;
    return {
      nombre_contacto: c.nombre_contacto,
      puesto_contacto: c.puesto_contacto ?? "",
      telefono_contacto: c.telefono_contacto ?? "",
      email_contacto: c.email_contacto ?? "",
    };
  };

  const total = esAlta ? contactosNuevos.length : itemsServidor.length;

  return (
    <>
      <div className="sec">
        <span>Contactos ({total})</span>
        {canWrite && !adding && !editando && (
          <button type="button" className="btn btn-xs" onClick={() => setAdding(true)}>
            + Agregar
          </button>
        )}
      </div>

      {adding && (
        <ContactoInlineForm
          title="Nuevo contacto"
          submitting={crear.isPending}
          onSubmit={onCrear}
          onCancel={cerrarForm}
        />
      )}

      {!esAlta && contactosServidor.isLoading && (
        <div className="state-msg">Cargando contactos…</div>
      )}
      {!esAlta && contactosServidor.isError && (
        <div className="state-msg error">No se pudieron cargar los contactos.</div>
      )}
      {total === 0 && !adding && <div className="fv muted">Sin contactos registrados.</div>}

      {esAlta
        ? contactosNuevos.map((c, idx) =>
            editingIndex === idx ? (
              <ContactoInlineForm
                key={idx}
                title="Editar contacto"
                defaultValues={editandoDefaultValues()}
                onSubmit={onActualizar}
                onCancel={cerrarForm}
              />
            ) : (
              <FilaContacto
                key={idx}
                nombre={c.nombre_contacto}
                puesto={c.puesto_contacto}
                telefono={c.telefono_contacto}
                email={c.email_contacto}
                canWrite={canWrite}
                onEditar={() => setEditingIndex(idx)}
                accionSecundaria={{ label: "Quitar", onClick: () => quitarLocal(idx), danger: true }}
              />
            ),
          )
        : itemsServidor.map((c) =>
            editingServerId === c.contacto_agencia_id ? (
              <ContactoInlineForm
                key={c.contacto_agencia_id}
                title="Editar contacto"
                defaultValues={editandoDefaultValues()}
                submitting={actualizar.isPending}
                onSubmit={onActualizar}
                onCancel={cerrarForm}
              />
            ) : (
              <FilaContacto
                key={c.contacto_agencia_id}
                nombre={c.nombre_contacto}
                puesto={c.puesto_contacto}
                telefono={c.telefono_contacto}
                email={c.email_contacto}
                activo={c.activo}
                canWrite={canWrite}
                onEditar={() => setEditingServerId(c.contacto_agencia_id)}
                accionSecundaria={{
                  label: c.activo ? "Desactivar" : "Activar",
                  onClick: () =>
                    setEstado.mutateAsync({ id: c.contacto_agencia_id, activo: !c.activo }),
                  danger: c.activo,
                  loading: setEstado.isPending,
                }}
              />
            ),
          )}
    </>
  );
}

interface FilaContactoProps {
  nombre: string;
  puesto?: string | null;
  telefono?: string | null;
  email?: string | null;
  activo?: boolean;
  canWrite: boolean;
  onEditar: () => void;
  accionSecundaria: { label: string; onClick: () => void; danger?: boolean; loading?: boolean };
}

function FilaContacto({
  nombre,
  puesto,
  telefono,
  email,
  activo,
  canWrite,
  onEditar,
  accionSecundaria,
}: FilaContactoProps) {
  return (
    <div className="rel-item">
      <div>
        <div className="rel-name">{nombre}</div>
        <div className="rel-sub">
          {[puesto, telefono, email].filter(Boolean).join(" · ") || "Sin más datos"}
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        {activo != null && <StatusBadge activo={activo} labelActivo="Act" labelInactivo="Inact" />}
        {canWrite && (
          <>
            <button type="button" className="btn btn-xs" onClick={onEditar}>
              Editar
            </button>
            <button
              type="button"
              className={`btn btn-xs ${accionSecundaria.danger ? "btn-danger" : ""}`}
              disabled={accionSecundaria.loading}
              onClick={accionSecundaria.onClick}
            >
              {accionSecundaria.label}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
