/** Pantalla del catálogo Plaza: lista + panel de detalle (patrón F0).
 *
 * Filtros Activos/Inactivos/Todos + búsqueda + paginación por página. Alta/edición con
 * formulario en el panel derecho. La baja lógica que choca con dependientes activos
 * (afiliados/estaciones) pide confirmación y reintenta con `forzar`.
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import type { ListParams } from "@/shared/types";
import {
  CatalogToolbar,
  ConfirmDialog,
  DetailEmpty,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { PlazaForm } from "../components/PlazaForm";
import { usePlazas } from "../hooks";
import type { Plaza, PlazaCreate } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activos" },
  { key: "inactivos", label: "Inactivos" },
  { key: "todos", label: "Todos" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

export function PlazaCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = usePlazas();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Plaza | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [confirmBaja, setConfirmBaja] = useState<{ plaza: Plaza; message: string } | null>(null);

  const params: ListParams = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  const reset = () => {
    setSelected(null);
    setModo("view");
  };

  const seleccionar = (p: Plaza) => {
    setSelected(p);
    setModo("view");
  };

  const onCrear = async (data: PlazaCreate) => {
    const nueva = await crear.mutateAsync(data);
    setSelected(nueva);
    setModo("view");
  };

  const onActualizar = async (data: PlazaCreate) => {
    if (!selected) return;
    const upd = await actualizar.mutateAsync({ id: selected.plaza_id, data });
    setSelected(upd);
    setModo("view");
  };

  const cambiarEstado = async (p: Plaza, activo: boolean, forzar = false) => {
    try {
      const upd = await setEstado.mutateAsync({ id: p.plaza_id, activo, forzar });
      setSelected(upd);
      setConfirmBaja(null);
    } catch (e) {
      if (e instanceof ApiRequestError && e.codigo === "dependencias_activas") {
        const d = (e.detalles ?? {}) as { afiliados_activos?: number; estaciones_activas?: number };
        const partes = [
          d.afiliados_activos ? `${d.afiliados_activos} afiliado(s) activo(s)` : null,
          d.estaciones_activas ? `${d.estaciones_activas} estación(es) activa(s)` : null,
        ].filter(Boolean);
        setConfirmBaja({
          plaza: p,
          message: `Esta plaza tiene ${partes.join(" y ")} que dependen de ella. ¿Desactivarla de todos modos?`,
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
      <PlazaForm
        title="Nueva plaza"
        submitting={crear.isPending}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <PlazaForm
        title={`Editar: ${selected.nombre_plaza}`}
        defaultValues={{ nombre_plaza: selected.nombre_plaza, estado: selected.estado ?? "" }}
        submitting={actualizar.isPending}
        onSubmit={onActualizar}
        onCancel={() => setModo("view")}
      />
    );
  } else if (selected) {
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.nombre_plaza}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                {selected.estado && <span>{selected.estado}</span>}
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
          <div className="sec">Datos de la plaza</div>
          <div className="fl">Nombre</div>
          <div className="fv">{selected.nombre_plaza}</div>
          <div className="fl">Estado</div>
          <div className="fv">{selected.estado ?? "—"}</div>
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
    detail = <DetailEmpty message="Selecciona una plaza para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Plaza</th>
            <th>Estado</th>
            <th className="td-center" style={{ width: 90 }}>
              Estaciones
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr
              key={p.plaza_id}
              className={selected?.plaza_id === p.plaza_id ? "sel" : ""}
              onClick={() => seleccionar(p)}
            >
              <td className="td-main">{p.nombre_plaza}</td>
              <td className="td-2">{p.estado ?? "—"}</td>
              <td className="td-center td-2">{p.estaciones_count}</td>
              <td className="td-center">
                <StatusBadge activo={p.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando plazas…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las plazas.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay plazas para el filtro seleccionado.</div>
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
          <div className="cat-title">Plazas</div>
          <div className="cat-sub">Plazas geográficas donde operan los afiliados.</div>
        </div>
        {canWrite && (
          <button
            type="button"
            className="btn btn-phase"
            onClick={() => {
              setSelected(null);
              setModo("new");
            }}
          >
            + Nueva plaza
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar plaza o estado…"
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
        title="Desactivar plaza"
        message={confirmBaja?.message ?? ""}
        confirmLabel="Desactivar"
        danger
        loading={setEstado.isPending}
        onConfirm={() => confirmBaja && cambiarEstado(confirmBaja.plaza, false, true)}
        onCancel={() => setConfirmBaja(null)}
      />
    </>
  );
}
