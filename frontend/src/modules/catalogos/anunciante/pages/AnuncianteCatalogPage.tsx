/** Pantalla del catálogo Anunciante: lista + panel de detalle (patrón F0).
 *
 * Filtros de Estatus (Activos/Inactivos/Todos) y de Relación (Todas / Vía agencia /
 * Directo), búsqueda y paginación. El detalle muestra identificación, contacto, días de
 * crédito (sensible), marcas anidadas, contratos e historial. La baja con marcas o
 * contratos activos pide confirmación y reintenta con `forzar`.
 */

import { useState } from "react";

import { useAgencias } from "@/modules/catalogos/agencia/hooks";
import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import { CatalogToolbar, ConfirmDialog, DetailEmpty, ListDetailLayout, Paginator, StatusBadge } from "@/shared/ui";

import type { AnuncianteListParams } from "../api";
import { AnuncianteDetailPanel } from "../components/AnuncianteDetailPanel";
import { AnuncianteForm, type AnuncianteFormOutput } from "../components/AnuncianteForm";
import { useAnunciantes } from "../hooks";
import type { Anunciante, Relacion } from "../types";

type Filtro = "todos" | "activos" | "inactivos";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "activos", label: "Activos" },
  { key: "inactivos", label: "Inactivos" },
  { key: "todos", label: "Todos" },
];

const RELACIONES: { key: Relacion; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "via_agencia", label: "Vía agencia" },
  { key: "directo", label: "Sin agencia" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activos" ? true : f === "inactivos" ? false : undefined;

const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

export function AnuncianteCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useAnunciantes();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [relacion, setRelacion] = useState<Relacion>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Anunciante | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [confirmBaja, setConfirmBaja] = useState<{ message: string } | null>(null);

  const params: AnuncianteListParams = {
    page,
    size,
    activo: activoDeFiltro(filtro),
    q: q || undefined,
    relacion,
  };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  // Agencias activas para el select del formulario.
  const agenciasQuery = useAgencias().useList({ activo: true, size: 100 });
  const agencias = (agenciasQuery.data?.items ?? []).map((a) => ({
    agencia_id: a.agencia_id,
    nombre_agencia: a.nombre_agencia,
  }));

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
  };

  const seleccionar = (a: Anunciante) => {
    setSelected(a);
    setModo("view");
    setSubmitError(null);
  };

  const manejarSubmitError = (e: unknown) => {
    if (
      e instanceof ApiRequestError &&
      ["conflicto", "validacion", "sin_permiso", "error_dominio", "no_encontrado"].includes(e.codigo)
    ) {
      setSubmitError(e.message);
      return;
    }
    throw e;
  };

  const onCrear = async (data: AnuncianteFormOutput) => {
    setSubmitError(null);
    try {
      const nuevo = await crear.mutateAsync(data);
      setSelected(nuevo);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: AnuncianteFormOutput) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.anunciante_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (a: Anunciante, activo: boolean, forzar = false) => {
    try {
      const upd = await setEstado.mutateAsync({ id: a.anunciante_id, activo, forzar });
      setSelected(upd);
      setConfirmBaja(null);
    } catch (e) {
      if (e instanceof ApiRequestError && e.codigo === "dependencias_activas") {
        const d = (e.detalles ?? {}) as { marcas_activas?: number; contratos_activos?: number };
        const partes = [
          d.marcas_activas ? `${d.marcas_activas} marca(s) activa(s)` : null,
          d.contratos_activos ? `${d.contratos_activos} contrato(s) activo(s)` : null,
        ].filter(Boolean);
        setConfirmBaja({
          message: `Este anunciante tiene ${partes.join(" y ")}. ¿Desactivarlo de todos modos?`,
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
      <AnuncianteForm
        title="Nuevo anunciante"
        agencias={agencias}
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <AnuncianteForm
        title={`Editar: ${selected.nombre_comercial}`}
        agencias={agencias}
        isEdit
        diasOriginal={String(selected.dias_credito_default)}
        defaultValues={{
          nombre_comercial: selected.nombre_comercial,
          nombre_fiscal: selected.nombre_fiscal,
          rfc_anunciante: selected.rfc_anunciante,
          agencia_id: selected.agencia_id ?? "",
          localizacion: selected.localizacion ?? "",
          referencia_anunciante: selected.referencia_anunciante ?? "",
          contacto_nombre: selected.contacto_nombre ?? "",
          contacto_email: selected.contacto_email ?? "",
          contacto_telefono: selected.contacto_telefono ?? "",
          dias_credito_default: String(selected.dias_credito_default),
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
      <AnuncianteDetailPanel
        anunciante={selected}
        canWrite={canWrite}
        onEdit={() => setModo("edit")}
        onToggleActivo={() => cambiarEstado(selected, !selected.activo)}
        togglingActivo={setEstado.isPending}
      />
    );
  } else {
    detail = (
      <DetailEmpty message="Selecciona un anunciante para ver sus marcas, contratos y datos comerciales." />
    );
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Nombre comercial</th>
            <th>Razón social</th>
            <th style={{ width: 120 }}>RFC</th>
            <th style={{ width: "18%" }}>Agencia</th>
            <th className="td-center" style={{ width: 80 }}>
              Crédito
            </th>
            <th className="td-center" style={{ width: 80 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr
              key={a.anunciante_id}
              className={selected?.anunciante_id === a.anunciante_id ? "sel" : ""}
              onClick={() => seleccionar(a)}
            >
              <td className="td-main">{a.nombre_comercial}</td>
              <td className="td-2">{a.nombre_fiscal}</td>
              <td className="td-mono">{a.rfc_anunciante}</td>
              <td className="td-2">
                {a.agencia_id ? (
                  a.agencia_nombre
                ) : (
                  <span style={{ color: "var(--text3)" }}>— Sin agencia —</span>
                )}
              </td>
              <td className="td-center td-2">{oGuion(String(a.dias_credito_default))} d</td>
              <td className="td-center">
                <StatusBadge activo={a.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando anunciantes…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los anunciantes.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay anunciantes para los filtros seleccionados.</div>
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
          <div className="cat-title">Anunciantes</div>
          <div className="cat-sub">
            Clientes comerciales. Cada anunciante puede tener marcas, contratos y representación
            por una agencia.
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
            + Nuevo anunciante
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
        filterLabel2="Relación"
        filters2={RELACIONES}
        activeFilter2={relacion}
        onFilter2={(k) => {
          setRelacion(k as Relacion);
          setPage(1);
        }}
        count={list.data ? `${items.length} de ${list.data.total}` : undefined}
      />
      <ListDetailLayout list={listNode} detail={detail} />

      <ConfirmDialog
        visible={confirmBaja !== null}
        title="Desactivar anunciante"
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
