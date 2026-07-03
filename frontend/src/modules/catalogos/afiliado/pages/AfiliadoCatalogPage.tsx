/** Pantalla del catálogo "Afiliados y estaciones": lista de afiliados + panel de detalle
 * con estaciones anidadas (patrón de la pantalla aprobada F0).
 *
 * Baja lógica del afiliado con confirmación cuando tiene estaciones activas (409
 * `dependencias_activas` → confirmar → reintento con `forzar`).
 */

import { useState } from "react";

import { usePlazas } from "@/modules/catalogos/plaza/hooks";
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

import { AfiliadoDetailPanel } from "../components/AfiliadoDetailPanel";
import { AfiliadoForm } from "../components/AfiliadoForm";
import { useAfiliados } from "../hooks";
import type { Afiliado, AfiliadoCreate } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activos" },
  { key: "inactivos", label: "Inactivos" },
  { key: "todos", label: "Todos" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

export function AfiliadoCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useAfiliados();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Afiliado | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [confirmBaja, setConfirmBaja] = useState<{ message: string } | null>(null);

  const params: ListParams = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  // Plazas activas para el select del formulario y para resolver el nombre en el detalle.
  const plazasQuery = usePlazas().useList({ activo: true, size: 100 });
  const plazas = plazasQuery.data?.items ?? [];

  const reset = () => {
    setSelected(null);
    setModo("view");
  };

  const onCrear = async (data: AfiliadoCreate) => {
    const nuevo = await crear.mutateAsync(data);
    setSelected(nuevo);
    setModo("view");
  };

  const onActualizar = async (data: AfiliadoCreate) => {
    if (!selected) return;
    const upd = await actualizar.mutateAsync({ id: selected.afiliado_id, data });
    setSelected(upd);
    setModo("view");
  };

  const cambiarEstado = async (a: Afiliado, activo: boolean, forzar = false) => {
    try {
      const upd = await setEstado.mutateAsync({ id: a.afiliado_id, activo, forzar });
      setSelected(upd);
      setConfirmBaja(null);
    } catch (e) {
      if (e instanceof ApiRequestError && e.codigo === "dependencias_activas") {
        const d = (e.detalles ?? {}) as { estaciones_activas?: number };
        setConfirmBaja({
          message: `Este afiliado tiene ${d.estaciones_activas ?? ""} estación(es) activa(s). ¿Desactivarlo de todos modos?`,
        });
      } else {
        throw e;
      }
    }
  };

  // ── detalle ─────────────────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <AfiliadoForm
        title="Nuevo afiliado"
        plazas={plazas}
        submitting={crear.isPending}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <AfiliadoForm
        title={`Editar: ${selected.nombre_afiliado}`}
        plazas={plazas}
        defaultValues={{
          nombre_afiliado: selected.nombre_afiliado,
          razon_social_afiliado: selected.razon_social_afiliado,
          rfc_afiliado: selected.rfc_afiliado,
          plaza_id: selected.plaza_id,
          contacto_nombre: selected.contacto_nombre ?? "",
          contacto_email: selected.contacto_email ?? "",
          contacto_telefono: selected.contacto_telefono ?? "",
        }}
        submitting={actualizar.isPending}
        onSubmit={onActualizar}
        onCancel={() => setModo("view")}
      />
    );
  } else if (selected) {
    detail = (
      <AfiliadoDetailPanel
        afiliado={selected}
        plazas={plazas}
        canWrite={canWrite}
        onEdit={() => setModo("edit")}
        onToggleActivo={() => cambiarEstado(selected, !selected.activo)}
        togglingActivo={setEstado.isPending}
      />
    );
  } else {
    detail = <DetailEmpty message="Selecciona un afiliado para ver sus estaciones." />;
  }

  // ── lista ─────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Afiliado</th>
            <th style={{ width: "18%" }}>Plaza principal</th>
            <th style={{ width: 130 }}>RFC</th>
            <th className="td-center" style={{ width: 90 }}>
              Estaciones
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr
              key={a.afiliado_id}
              className={selected?.afiliado_id === a.afiliado_id ? "sel" : ""}
              onClick={() => {
                setSelected(a);
                setModo("view");
              }}
            >
              <td className="td-main">
                {a.nombre_afiliado}
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text3)",
                    marginTop: 2,
                    fontWeight: 400,
                  }}
                >
                  {a.razon_social_afiliado}
                </div>
              </td>
              <td className="td-2">{a.plaza_nombre ?? "—"}</td>
              <td className="td-mono">{a.rfc_afiliado}</td>
              <td className="td-center td-2">{a.estaciones_count}</td>
              <td className="td-center">
                <StatusBadge activo={a.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando afiliados…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los afiliados.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay afiliados para el filtro seleccionado.</div>
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
          <div className="cat-title">Afiliados y estaciones</div>
          <div className="cat-sub">
            Empresas que operan estaciones. Cada afiliado opera en una plaza; sus estaciones
            la heredan.
          </div>
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
            + Nuevo afiliado
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar nombre, razón social o RFC…"
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
        title="Desactivar afiliado"
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
