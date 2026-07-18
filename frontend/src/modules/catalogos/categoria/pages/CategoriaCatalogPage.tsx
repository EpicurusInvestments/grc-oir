/** Pantalla del catálogo Categoria (menú "Soporte"): lista + panel de detalle (patrón F0).
 *
 * Catálogo simple (sin campos sensibles). Filtros Activos/Inactivos/Todos, búsqueda y
 * paginación. `nombre_categoria` único CI (409 `conflicto` desde el backend → submitError).
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

import { CategoriaForm } from "../components/CategoriaForm";
import { useCategorias } from "../hooks";
import type { Categoria, CategoriaCreate } from "../types";

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

export function CategoriaCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useCategorias();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Categoria | null>(null);
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

  const seleccionar = (c: Categoria) => {
    setSelected(c);
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

  const onCrear = async (data: CategoriaCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: CategoriaCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.categoria_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (c: Categoria, activo: boolean) => {
    const upd = await setEstado.mutateAsync({ id: c.categoria_id, activo });
    setSelected(upd);
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <CategoriaForm
        title="Nueva categoría"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <CategoriaForm
        title={`Editar: ${selected.nombre_categoria}`}
        defaultValues={{
          nombre_categoria: selected.nombre_categoria,
          descripcion_categoria: selected.descripcion_categoria ?? "",
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
              <div className="dh-name">{selected.nombre_categoria}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
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
          <div className="sec">Datos de la categoría</div>
          <div className="fl">Descripción</div>
          <div className="fv muted">{oGuion(selected.descripcion_categoria)}</div>
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
    detail = <DetailEmpty message="Selecciona una categoría para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: "30%" }}>Categoría</th>
            <th>Descripción</th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr
              key={c.categoria_id}
              className={selected?.categoria_id === c.categoria_id ? "sel" : ""}
              onClick={() => seleccionar(c)}
            >
              <td className="td-main">{c.nombre_categoria}</td>
              <td className="td-2">{oGuion(c.descripcion_categoria)}</td>
              <td className="td-center">
                <StatusBadge activo={c.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando categorías…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las categorías.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay categorías para el filtro seleccionado.</div>
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
          <div className="cat-title">Categorías comerciales</div>
          <div className="cat-sub">Categorías de industria para segmentar órdenes y reportes.</div>
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
            + Nueva categoría
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar categoría…"
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
