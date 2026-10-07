/** Pantalla del catálogo Producto Duración (menú "Operación"): lista + panel de detalle
 * (patrón F0).
 *
 * ADR-159 (petición del usuario): catálogo NUEVO, fuera de la spec BD v2 y desconectado
 * del enum `DuracionSpot` que usan Tarifa/Órdenes — por ahora NINGUNA otra pantalla lo
 * usa, es solo el CRUD. Filtros Activos/Inactivos/Todos, búsqueda y paginación. Sin
 * duplicado por (producto + descripción) case-insensitive — 409 `conflicto` desde el
 * backend → `submitError`.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import type { ListParams } from "@/shared/types";
import {
  CatalogToolbar,
  DetailEmpty,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { DuracionSpotForm } from "../components/DuracionSpotForm";
import { useDuracionesSpot } from "../hooks";
import type { DuracionSpotCatalogo, DuracionSpotCatalogoCreate } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activos" },
  { key: "inactivos", label: "Inactivos" },
  { key: "todos", label: "Todos" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

export function DuracionSpotCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useDuracionesSpot();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<DuracionSpotCatalogo | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const params: ListParams = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
  };

  const seleccionar = (d: DuracionSpotCatalogo) => {
    setSelected(d);
    setModo("view");
    setSubmitError(null);
  };

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

  const onCrear = async (data: DuracionSpotCatalogoCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: DuracionSpotCatalogoCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.duracion_spot_catalogo_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (d: DuracionSpotCatalogo, activo: boolean) => {
    const upd = await setEstado.mutateAsync({ id: d.duracion_spot_catalogo_id, activo });
    setSelected(upd);
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <DuracionSpotForm
        title="Nueva duración"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <DuracionSpotForm
        title={`Editar: ${selected.descripcion_duracion}`}
        defaultValues={{
          producto: selected.producto,
          descripcion_duracion: selected.descripcion_duracion,
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
              <div className="dh-name">{selected.descripcion_duracion}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className="badge b-blue">{selected.producto}</span>
              </div>
            </div>
            {canWrite && (
              <button type="button" className="btn btn-sm" onClick={() => setModo("edit")}>
                Editar
              </button>
            )}
          </div>
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
    detail = <DetailEmpty message="Selecciona una duración para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: "30%" }}>Producto</th>
            <th>Descripción de la duración</th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr
              key={d.duracion_spot_catalogo_id}
              className={
                selected?.duracion_spot_catalogo_id === d.duracion_spot_catalogo_id ? "sel" : ""
              }
              onClick={() => seleccionar(d)}
            >
              <td className="td-main">{d.producto}</td>
              <td className="td-2">{d.descripcion_duracion}</td>
              <td className="td-center">
                <StatusBadge activo={d.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando duraciones…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las duraciones.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay duraciones para el filtro seleccionado.</div>
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
          <div className="cat-title">Producto Duración</div>
          <div className="cat-sub">
            Catálogo de duraciones administrables por producto (producto y duración de
            captura libre). Aún no se usa en otras pantallas.
          </div>
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
            + Nueva duración
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar por descripción de duración…"
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
