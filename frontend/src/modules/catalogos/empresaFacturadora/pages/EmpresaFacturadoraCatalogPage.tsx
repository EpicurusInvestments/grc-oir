/** Pantalla del catálogo EmpresaFacturadora (menú "Soporte"): lista + panel de detalle.
 *
 * Catálogo simple (sin campos sensibles). Columnas: Empresa · RFC · Estatus; la dirección
 * se muestra en el detalle. RFC único (409 `conflicto` desde el backend → submitError).
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

import { EmpresaFacturadoraForm } from "../components/EmpresaFacturadoraForm";
import { useEmpresasFacturadoras } from "../hooks";
import type { EmpresaFacturadora, EmpresaFacturadoraCreate } from "../types";

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

export function EmpresaFacturadoraCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useEmpresasFacturadoras();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<EmpresaFacturadora | null>(null);
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

  const seleccionar = (e: EmpresaFacturadora) => {
    setSelected(e);
    setModo("view");
    setSubmitError(null);
  };

  const manejarSubmitError = (err: unknown) => {
    if (
      err instanceof ApiRequestError &&
      ["conflicto", "validacion", "sin_permiso", "error_dominio"].includes(err.codigo)
    ) {
      setSubmitError(err.message);
      return;
    }
    throw err;
  };

  const onCrear = async (data: EmpresaFacturadoraCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: EmpresaFacturadoraCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.empresa_facturadora_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (e: EmpresaFacturadora, activo: boolean) => {
    const upd = await setEstado.mutateAsync({ id: e.empresa_facturadora_id, activo });
    setSelected(upd);
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <EmpresaFacturadoraForm
        title="Nueva empresa facturadora"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <EmpresaFacturadoraForm
        title={`Editar: ${selected.nombre_empresa}`}
        defaultValues={{
          nombre_empresa: selected.nombre_empresa,
          rfc_empresa: selected.rfc_empresa,
          direccion_empresa: selected.direccion_empresa ?? "",
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
              <div className="dh-name">{selected.nombre_empresa}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className="mono">{selected.rfc_empresa}</span>
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
          <div className="fv mono">{selected.rfc_empresa}</div>
          <div className="fl">Dirección</div>
          <div className="fv muted">{oGuion(selected.direccion_empresa)}</div>
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
    detail = <DetailEmpty message="Selecciona una empresa facturadora para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Empresa</th>
            <th style={{ width: 140 }}>RFC</th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr
              key={e.empresa_facturadora_id}
              className={selected?.empresa_facturadora_id === e.empresa_facturadora_id ? "sel" : ""}
              onClick={() => seleccionar(e)}
            >
              <td className="td-main">{e.nombre_empresa}</td>
              <td className="td-mono">{e.rfc_empresa}</td>
              <td className="td-center">
                <StatusBadge activo={e.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando empresas…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las empresas.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay empresas para el filtro seleccionado.</div>
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
          <div className="cat-title">Empresas facturadoras</div>
          <div className="cat-sub">Razones sociales del grupo que emiten facturas.</div>
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
            + Nueva empresa facturadora
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar empresa o RFC…"
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
