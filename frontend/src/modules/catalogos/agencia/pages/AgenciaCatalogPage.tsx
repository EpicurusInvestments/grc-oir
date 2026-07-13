/** Pantalla del catálogo Agencia: lista + panel de detalle (patrón F0).
 *
 * Filtros Activas/Inactivas/Todas + búsqueda + paginación. El % de comisión es PARÁMETRO
 * SENSIBLE: se muestra con tag «Audit log» en el detalle y con `SensitiveField` (+ motivo,
 * solo al cambiarlo) en el formulario. El panel de detalle muestra, además, los anunciantes
 * representados y el historial de cambios (auditoría). La baja con anunciantes activos pide
 * confirmación y reintenta con `forzar`. Errores de negocio (409 nombre, 422 RFC) → form.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import type { ListParams } from "@/shared/types";
import {
  CatalogToolbar,
  ConfirmDialog,
  DetailEmpty,
  FieldTag,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { AgenciaForm, type AgenciaFormOutput } from "../components/AgenciaForm";
import { useAgencias, useAnunciantesPorAgencia, useHistorialAgencia } from "../hooks";
import type { Agencia } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activas" },
  { key: "inactivos", label: "Inactivas" },
  { key: "todos", label: "Todas" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

/** Campo opcional vacío/nulo → guión (evita mostrar cadenas residuales). */
const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

/** Etiqueta legible para los campos auditados; fallback al nombre técnico. */
const CAMPO_LABEL: Record<string, string> = {
  porcentaje_comision_agencia_default: "% comisión",
};
const labelCampo = (c: string) => CAMPO_LABEL[c] ?? c;

const fmtFechaHora = (iso: string): string =>
  new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });

export function AgenciaCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useAgencias();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Agencia | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [confirmBaja, setConfirmBaja] = useState<{ message: string } | null>(null);

  const params: ListParams = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  // Secciones del panel de detalle (solo cuando hay agencia seleccionada).
  const anunciantes = useAnunciantesPorAgencia(selected?.agencia_id ?? null);
  const historial = useHistorialAgencia(selected?.agencia_id ?? null);

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
  };

  const seleccionar = (a: Agencia) => {
    setSelected(a);
    setModo("view");
    setSubmitError(null);
  };

  const nuevo = () => {
    setSelected(null);
    setModo("new");
    setSubmitError(null);
  };

  /** Traduce errores de dominio del backend a un mensaje del formulario; relanza el resto. */
  const manejarSubmitError = (e: unknown) => {
    if (
      e instanceof ApiRequestError &&
      ["conflicto", "validacion", "sin_permiso", "error_dominio"].includes(e.codigo)
    ) {
      setSubmitError(e.message);
      return;
    }
    throw e;
  };

  const onCrear = async (data: AgenciaFormOutput) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: AgenciaFormOutput) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.agencia_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (a: Agencia, activo: boolean, forzar = false) => {
    try {
      const upd = await setEstado.mutateAsync({ id: a.agencia_id, activo, forzar });
      setSelected(upd);
      setConfirmBaja(null);
    } catch (e) {
      if (e instanceof ApiRequestError && e.codigo === "dependencias_activas") {
        const d = (e.detalles ?? {}) as { anunciantes_activos?: number };
        setConfirmBaja({
          message: `Esta agencia tiene ${d.anunciantes_activos ?? ""} anunciante(s) activo(s). ¿Desactivarla de todos modos?`,
        });
      } else {
        throw e;
      }
    }
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <AgenciaForm
        title="Nueva agencia"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <AgenciaForm
        title={`Editar: ${selected.nombre_agencia}`}
        isEdit
        comisionOriginal={selected.porcentaje_comision_agencia_default}
        defaultValues={{
          nombre_agencia: selected.nombre_agencia,
          rfc_agencia: selected.rfc_agencia,
          contacto_nombre: selected.contacto_nombre ?? "",
          contacto_email: selected.contacto_email ?? "",
          contacto_telefono: selected.contacto_telefono ?? "",
          porcentaje_comision_agencia_default: selected.porcentaje_comision_agencia_default,
        }}
        submitting={actualizar.isPending}
        submitError={submitError}
        onSubmit={onActualizar}
        onCancel={() => {
          setModo("view");
          setSubmitError(null);
        }}
      />
    );
  } else if (selected) {
    const anunItems = anunciantes.data?.items ?? [];
    const histItems = historial.data ?? [];
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.nombre_agencia}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className="badge b-blue">{selected.anunciantes_count} anunciante(s)</span>
              </div>
            </div>
            {canWrite && (
              <button type="button" className="btn btn-sm" onClick={() => setModo("edit")}>
                Editar
              </button>
            )}
          </div>
        </div>
        <div className="db">
          <div className="sec">Datos fiscales</div>
          <div className="fl">RFC</div>
          <div className="fv mono">{selected.rfc_agencia}</div>

          <div className="sec">Comisión</div>
          <div className="fl">
            % comisión por defecto <FieldTag origin="audit" />
          </div>
          <div className="fv mono">{selected.porcentaje_comision_agencia_default}%</div>

          <div className="sec">Contacto</div>
          <div className="fl">Nombre</div>
          <div className="fv">{oGuion(selected.contacto_nombre)}</div>
          <div className="fl">Correo</div>
          <div className="fv link">{oGuion(selected.contacto_email)}</div>
          <div className="fl">Teléfono</div>
          <div className="fv">{oGuion(selected.contacto_telefono)}</div>

          <div className="sec">Anunciantes representados ({selected.anunciantes_count})</div>
          {anunciantes.isLoading && <div className="state-msg">Cargando anunciantes…</div>}
          {anunciantes.isError && (
            <div className="state-msg error">No se pudieron cargar los anunciantes.</div>
          )}
          {!anunciantes.isLoading && !anunciantes.isError && anunItems.length === 0 && (
            <div className="fv muted">Sin anunciantes registrados.</div>
          )}
          {anunItems.map((an) => (
            <div className="rel-item" key={an.anunciante_id}>
              <div>
                <div className="rel-name">{an.nombre_comercial}</div>
                <div className="rel-sub mono">{an.rfc_anunciante}</div>
              </div>
              <StatusBadge activo={an.activo} labelActivo="Act" labelInactivo="Inact" />
            </div>
          ))}

          <div className="sec">Historial de cambios</div>
          {historial.isLoading && <div className="state-msg">Cargando historial…</div>}
          {historial.isError && (
            <div className="state-msg error">No se pudo cargar el historial.</div>
          )}
          {!historial.isLoading && !historial.isError && histItems.length === 0 && (
            <div className="fv muted">Sin cambios registrados.</div>
          )}
          {histItems.map((h) => (
            <div className="rel-item" key={h.log_cambio_parametro_id}>
              <div>
                <div className="rel-name">
                  {labelCampo(h.campo)}: <span className="mono">{oGuion(h.valor_anterior)}</span> →{" "}
                  <span className="mono">{oGuion(h.valor_nuevo)}</span>
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
              className={`btn btn-sm ${selected.activo ? "btn-danger" : ""}`}
              disabled={setEstado.isPending}
              onClick={() => cambiarEstado(selected, !selected.activo)}
            >
              {selected.activo ? "Desactivar" : "Activar"}
            </button>
          </div>
        )}
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona una agencia para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Agencia</th>
            <th style={{ width: 120 }}>RFC</th>
            <th>Contacto</th>
            <th className="td-center" style={{ width: 90 }}>
              % comisión
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Anunciantes
            </th>
            <th className="td-center" style={{ width: 80 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr
              key={a.agencia_id}
              className={selected?.agencia_id === a.agencia_id ? "sel" : ""}
              onClick={() => seleccionar(a)}
            >
              <td className="td-main">{a.nombre_agencia}</td>
              <td className="td-mono">{a.rfc_agencia}</td>
              <td className="td-2">{oGuion(a.contacto_nombre)}</td>
              <td className="td-center td-2">{a.porcentaje_comision_agencia_default}%</td>
              <td className="td-center td-2">{a.anunciantes_count}</td>
              <td className="td-center">
                <StatusBadge activo={a.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando agencias…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las agencias.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay agencias para el filtro seleccionado.</div>
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
          <div className="cat-title">Agencias</div>
          <div className="cat-sub">Agencias de publicidad que representan anunciantes.</div>
        </div>
        {canWrite && (
          <button type="button" className="btn btn-phase" onClick={nuevo}>
            + Nueva agencia
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar nombre o RFC…"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setPage(1);
          reset();
        }}
        count={list.data ? `${items.length} de ${list.data.total}` : undefined}
      />
      <ListDetailLayout list={listNode} detail={detail} />

      <ConfirmDialog
        visible={confirmBaja !== null}
        title="Desactivar agencia"
        message={confirmBaja?.message ?? ""}
        confirmLabel="Desactivar"
        danger
        loading={setEstado.isPending}
        onConfirm={() => selected && cambiarEstado(selected, false, true)}
        onCancel={() => setConfirmBaja(null)}
      />
    </>
  );
}
