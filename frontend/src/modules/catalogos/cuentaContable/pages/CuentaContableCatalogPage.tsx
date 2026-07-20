/** Pantalla del catálogo CuentaContable (menú "Soporte"): lista + panel de detalle.
 *
 * Catálogo simple (sin campos sensibles ni carga CSV). Columnas: Código · Nombre · Tipo ·
 * Estatus. `codigo_cuenta` único CI (409 `conflicto` desde el backend → submitError);
 * `tipo_cuenta` es un ENUM que se muestra como badge y se captura con un select.
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

import { CuentaContableForm } from "../components/CuentaContableForm";
import { useCuentasContables } from "../hooks";
import type { CuentaContable, CuentaContableCreate } from "../types";
import { TIPO_CUENTA_LABEL } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activas" },
  { key: "inactivos", label: "Inactivas" },
  { key: "todos", label: "Todas" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

export function CuentaContableCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useCuentasContables();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<CuentaContable | null>(null);
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

  const seleccionar = (c: CuentaContable) => {
    setSelected(c);
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

  const onCrear = async (data: CuentaContableCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: CuentaContableCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.cuenta_contable_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (c: CuentaContable, activo: boolean) => {
    const upd = await setEstado.mutateAsync({ id: c.cuenta_contable_id, activo });
    setSelected(upd);
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <CuentaContableForm
        title="Nueva cuenta contable"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <CuentaContableForm
        title={`Editar: ${selected.codigo_cuenta}`}
        defaultValues={{
          codigo_cuenta: selected.codigo_cuenta,
          nombre_cuenta: selected.nombre_cuenta,
          tipo_cuenta: selected.tipo_cuenta,
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
              <div className="dh-name">{selected.nombre_cuenta}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className="mono">{selected.codigo_cuenta}</span>
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
          <div className="sec">Datos de la cuenta</div>
          <div className="fl">Código</div>
          <div className="fv mono">{selected.codigo_cuenta}</div>
          <div className="fl">Tipo de cuenta</div>
          <div className="fv">
            <span className="badge b-purple">{TIPO_CUENTA_LABEL[selected.tipo_cuenta]}</span>
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
    detail = <DetailEmpty message="Selecciona una cuenta para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: 140 }}>Código</th>
            <th>Nombre</th>
            <th style={{ width: 100 }}>Tipo</th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr
              key={c.cuenta_contable_id}
              className={selected?.cuenta_contable_id === c.cuenta_contable_id ? "sel" : ""}
              onClick={() => seleccionar(c)}
            >
              <td className="td-mono">{c.codigo_cuenta}</td>
              <td className="td-main">{c.nombre_cuenta}</td>
              <td>
                <span className="badge b-purple">{TIPO_CUENTA_LABEL[c.tipo_cuenta]}</span>
              </td>
              <td className="td-center">
                <StatusBadge activo={c.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando cuentas…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las cuentas.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay cuentas para el filtro seleccionado.</div>
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
          <div className="cat-title">Cuentas contables</div>
          <div className="cat-sub">
            Catálogo contable interno (código, nombre y tipo) para clasificar ingresos, costos
            y gastos.
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
            + Nueva cuenta contable
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar código o nombre…"
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
