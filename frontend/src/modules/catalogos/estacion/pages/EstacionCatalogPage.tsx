/** Pantalla del catálogo Estaciones/Emisoras: lista + panel de detalle (patrón F0).
 *
 * ADR-094: pantalla propia — antes se administraba anidada dentro de Afiliados. Plaza y
 * Afiliado son dos datos independientes (la plaza de la estación ya no se hereda del
 * afiliado, reemplaza a ADR-005).
 */

import { useState } from "react";

import { useAfiliados } from "@/modules/catalogos/afiliado/hooks";
import { usePlazas } from "@/modules/catalogos/plaza/hooks";
import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator, StatusBadge } from "@/shared/ui";

import { EstacionForm } from "../components/EstacionForm";
import { useEstaciones } from "../hooks";
import type { Estacion, EstacionCreate, TipoSenal } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activas" },
  { key: "inactivos", label: "Inactivas" },
  { key: "todos", label: "Todas" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

const TIPO_BADGE: Record<TipoSenal, string> = { fm: "b-teal", am: "b-amber", tv: "b-blue" };

export function EstacionCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useEstaciones();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Estacion | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const params = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  // Plazas y afiliados activos, para los selects del formulario.
  const plazasQuery = usePlazas().useList({ activo: true, size: 100 });
  const plazas = plazasQuery.data?.items ?? [];
  const afiliadosQuery = useAfiliados().useList({ activo: true, size: 100 });
  const afiliados = afiliadosQuery.data?.items ?? [];

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
  };

  const seleccionar = (e: Estacion) => {
    setSelected(e);
    setModo("view");
    setSubmitError(null);
  };

  const manejarSubmitError = (e: unknown) => {
    if (
      e instanceof ApiRequestError &&
      ["conflicto", "validacion", "sin_permiso", "error_dominio", "no_encontrado"].includes(
        e.codigo,
      )
    ) {
      setSubmitError(e.message);
      return;
    }
    throw e;
  };

  const onCrear = async (data: EstacionCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: EstacionCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.estacion_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  // ── detalle ─────────────────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <EstacionForm
        title="Nueva estación"
        plazas={plazas}
        afiliados={afiliados}
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <EstacionForm
        title={`Editar: ${selected.nombre_estacion}`}
        plazas={plazas}
        afiliados={afiliados}
        defaultValues={{
          nombre_estacion: selected.nombre_estacion,
          siglas: selected.siglas ?? "",
          frecuencia: selected.frecuencia ?? "",
          tipo_senal: selected.tipo_senal,
          plaza_id: selected.plaza_id,
          afiliado_id: selected.afiliado_id,
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
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.nombre_estacion}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className={`badge ${TIPO_BADGE[selected.tipo_senal]}`}>
                  {selected.tipo_senal.toUpperCase()}
                </span>
                {selected.siglas && <span className="badge b-gray">{selected.siglas}</span>}
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
          <div className="sec">Identificación</div>
          <div className="fl">Siglas</div>
          <div className="fv mono">{oGuion(selected.siglas)}</div>
          <div className="fl">Frecuencia</div>
          <div className="fv mono">{oGuion(selected.frecuencia)}</div>
          <div className="fl">Tipo de señal</div>
          <div className="fv">{selected.tipo_senal.toUpperCase()}</div>

          <div className="sec">Operación</div>
          <div className="fl">Plaza</div>
          <div className="fv">{oGuion(selected.plaza_nombre)}</div>
          <div className="fl">Afiliado</div>
          <div className="fv">{oGuion(selected.afiliado_nombre)}</div>
        </div>
        {canWrite && (
          <div className="df">
            <button
              type="button"
              className={`btn btn-sm ${selected.activo ? "btn-danger" : ""}`}
              disabled={setEstado.isPending}
              onClick={() =>
                setEstado.mutateAsync({ id: selected.estacion_id, activo: !selected.activo })
              }
            >
              {selected.activo ? "Desactivar" : "Activar"}
            </button>
          </div>
        )}
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona una estación para ver el detalle." />;
  }

  // ── lista ─────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Estación</th>
            <th style={{ width: 90 }}>Siglas</th>
            <th style={{ width: 90 }}>Tipo</th>
            <th style={{ width: 90 }}>Frecuencia</th>
            <th style={{ width: "16%" }}>Plaza</th>
            <th style={{ width: "18%" }}>Afiliado</th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr
              key={e.estacion_id}
              className={selected?.estacion_id === e.estacion_id ? "sel" : ""}
              onClick={() => seleccionar(e)}
            >
              <td className="td-main">{e.nombre_estacion}</td>
              <td className="td-2 mono">{oGuion(e.siglas)}</td>
              <td className="td-2">
                <span className={`badge ${TIPO_BADGE[e.tipo_senal]}`}>
                  {e.tipo_senal.toUpperCase()}
                </span>
              </td>
              <td className="td-2 mono">{oGuion(e.frecuencia)}</td>
              <td className="td-2">{oGuion(e.plaza_nombre)}</td>
              <td className="td-2">{oGuion(e.afiliado_nombre)}</td>
              <td className="td-center">
                <StatusBadge activo={e.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando estaciones…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las estaciones.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay estaciones para el filtro seleccionado.</div>
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
          <div className="cat-title">Estaciones</div>
          <div className="cat-sub">Emisoras (AM/FM/TV) operadas por los afiliados.</div>
        </div>
        {canWrite && (
          <button
            type="button"
            className="btn btn-phase"
            onClick={() => {
              setSelected(null);
              setModo("new");
              setSubmitError(null);
            }}
          >
            + Nueva estación
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar nombre, siglas o frecuencia…"
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
    </>
  );
}
