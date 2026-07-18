/** Pantalla del catálogo Vendedor (menú "Soporte"): lista + panel de detalle (patrón F0).
 *
 * El % de comisión es PARÁMETRO SENSIBLE: tag «Audit log» en el detalle, `SensitiveField`
 * (+ motivo, solo al cambiar) en el formulario, e "Historial de cambios" en el panel —
 * idéntico a Agencia en F0-03. Escritura solo admin (UX; el backend valida siempre).
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import type { ListParams } from "@/shared/types";
import {
  CatalogToolbar,
  DetailEmpty,
  FieldTag,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { VendedorForm, type VendedorFormOutput } from "../components/VendedorForm";
import { useHistorialVendedor, useVendedores } from "../hooks";
import type { Vendedor } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activos" },
  { key: "inactivos", label: "Inactivos" },
  { key: "todos", label: "Todos" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

const CAMPO_LABEL: Record<string, string> = { porcentaje_comision_default: "% comisión" };
const labelCampo = (c: string) => CAMPO_LABEL[c] ?? c;

const fmtFechaHora = (iso: string): string =>
  new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });

export function VendedorCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useVendedores();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Vendedor | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const params: ListParams = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();
  const historial = useHistorialVendedor(selected?.vendedor_id ?? null);

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
  };

  const seleccionar = (v: Vendedor) => {
    setSelected(v);
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

  const onCrear = async (data: VendedorFormOutput) => {
    setSubmitError(null);
    try {
      const nuevo = await crear.mutateAsync(data);
      setSelected(nuevo);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: VendedorFormOutput) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.vendedor_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (v: Vendedor, activo: boolean) => {
    const upd = await setEstado.mutateAsync({ id: v.vendedor_id, activo });
    setSelected(upd);
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <VendedorForm
        title="Nuevo vendedor"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <VendedorForm
        title={`Editar: ${selected.nombre_vendedor}`}
        isEdit
        comisionOriginal={selected.porcentaje_comision_default}
        defaultValues={{
          nombre_vendedor: selected.nombre_vendedor,
          email_vendedor: selected.email_vendedor ?? "",
          porcentaje_comision_default: selected.porcentaje_comision_default,
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
    const histItems = historial.data ?? [];
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.nombre_vendedor}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span>{oGuion(selected.email_vendedor)}</span>
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
          <div className="sec">Contacto</div>
          <div className="fl">Correo</div>
          <div className="fv link">{oGuion(selected.email_vendedor)}</div>

          <div className="sec">Comisión</div>
          <div className="fl">
            % comisión default <FieldTag origin="audit" />
          </div>
          <div className="fv mono" style={{ fontSize: 18, fontWeight: 600 }}>
            {selected.porcentaje_comision_default}%
          </div>

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
                  {labelCampo(h.campo)}:{" "}
                  <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_anterior)}</span> →{" "}
                  <span style={{ fontFamily: "var(--mono)" }}>{oGuion(h.valor_nuevo)}</span>
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
    detail = <DetailEmpty message="Selecciona un vendedor para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Nombre</th>
            <th>Correo</th>
            <th className="td-center" style={{ width: 100 }}>
              % Comisión
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((v) => (
            <tr
              key={v.vendedor_id}
              className={selected?.vendedor_id === v.vendedor_id ? "sel" : ""}
              onClick={() => seleccionar(v)}
            >
              <td className="td-main">{v.nombre_vendedor}</td>
              <td className="td-2 td-mono" style={{ fontSize: 12 }}>
                {oGuion(v.email_vendedor)}
              </td>
              <td className="td-center td-mono">{v.porcentaje_comision_default}%</td>
              <td className="td-center">
                <StatusBadge activo={v.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando vendedores…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los vendedores.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay vendedores para el filtro seleccionado.</div>
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
          <div className="cat-title">Vendedores</div>
          <div className="cat-sub">
            Ejecutivos comerciales del grupo. El % de comisión default tiene log de auditoría.
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
            + Nuevo vendedor
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar nombre o correo…"
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
