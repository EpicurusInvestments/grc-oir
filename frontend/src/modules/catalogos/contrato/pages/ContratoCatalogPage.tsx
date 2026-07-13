/** Pantalla del catálogo Contrato: lista + panel de detalle (patrón F0).
 *
 * Filtros por estado (Todos / Vigentes / Finalizados), búsqueda y paginación. El detalle
 * muestra anunciante, vigencia+monto, % de comisión (sensible), condiciones, adjuntos
 * (placeholder S3), historial y la máquina de estados (transiciones válidas). El % usa
 * `SensitiveField` en el formulario. Escritura solo para admin (UX; el backend valida).
 */

import { useState } from "react";

import { useAnunciantes } from "@/modules/catalogos/anunciante/hooks";
import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import type { ContratoListParams } from "../api";
import { ContratoDetailPanel } from "../components/ContratoDetailPanel";
import { ContratoForm, type ContratoFormOutput } from "../components/ContratoForm";
import { fmtMonto, fmtPct } from "../format";
import { useContratos } from "../hooks";
import { type Contrato, type EstadoContrato, ESTADO_BADGE } from "../types";

type Filtro = "todos" | "vigente" | "finalizado";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todos", label: "Todos" },
  { key: "vigente", label: "Vigentes" },
  { key: "finalizado", label: "Finalizados" },
];

const estadoDeFiltro = (f: Filtro): EstadoContrato | undefined =>
  f === "vigente" ? "vigente" : f === "finalizado" ? "finalizado" : undefined;

export function ContratoCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado, useTransicionar } = useContratos();

  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Contrato | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [transicionError, setTransicionError] = useState<string | null>(null);

  const params: ContratoListParams = {
    page,
    size,
    q: q || undefined,
    estado: estadoDeFiltro(filtro),
  };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();
  const transicionar = useTransicionar();

  // Anunciantes activos para el select del formulario.
  const anunciantesQuery = useAnunciantes().useList({ activo: true, size: 100 });
  const anunciantes = (anunciantesQuery.data?.items ?? []).map((a) => ({
    anunciante_id: a.anunciante_id,
    nombre_comercial: a.nombre_comercial,
  }));

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
    setTransicionError(null);
  };

  const seleccionar = (c: Contrato) => {
    setSelected(c);
    setModo("view");
    setSubmitError(null);
    setTransicionError(null);
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

  const onCrear = async (data: ContratoFormOutput) => {
    setSubmitError(null);
    try {
      const nuevo = await crear.mutateAsync(data);
      setSelected(nuevo);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: ContratoFormOutput) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.contrato_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onToggleActivo = async () => {
    if (!selected) return;
    const upd = await setEstado.mutateAsync({ id: selected.contrato_id, activo: !selected.activo });
    setSelected(upd);
  };

  const onTransicionar = async (estado: EstadoContrato) => {
    if (!selected) return;
    setTransicionError(null);
    try {
      const upd = await transicionar.mutateAsync({ id: selected.contrato_id, estado });
      setSelected(upd);
    } catch (e) {
      if (e instanceof ApiRequestError && (e.codigo === "transicion_invalida" || e.codigo === "sin_permiso")) {
        setTransicionError(e.message);
      } else {
        throw e;
      }
    }
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <ContratoForm
        title="Nuevo contrato"
        anunciantes={anunciantes}
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <ContratoForm
        title={`Editar: ${selected.numero_contrato}`}
        anunciantes={anunciantes}
        isEdit
        comisionOriginal={selected.porcentaje_comision_contrato ?? ""}
        defaultValues={{
          anunciante_id: selected.anunciante_id,
          numero_contrato: selected.numero_contrato,
          nombre_contrato: selected.nombre_contrato,
          fecha_inicio_contrato: selected.fecha_inicio_contrato,
          fecha_fin_contrato: selected.fecha_fin_contrato,
          monto_contrato: selected.monto_contrato ?? "",
          porcentaje_comision_contrato: selected.porcentaje_comision_contrato ?? "",
          condiciones_comerciales: selected.condiciones_comerciales ?? "",
          observaciones_contrato: selected.observaciones_contrato ?? "",
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
      <ContratoDetailPanel
        contrato={selected}
        canWrite={canWrite}
        onEdit={() => setModo("edit")}
        onToggleActivo={onToggleActivo}
        togglingActivo={setEstado.isPending}
        onTransicionar={onTransicionar}
        transicionando={transicionar.isPending}
        transicionError={transicionError}
      />
    );
  } else {
    detail = <DetailEmpty message="Selecciona un contrato para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: 120 }}>Número</th>
            <th>Nombre</th>
            <th style={{ width: "20%" }}>Anunciante</th>
            <th style={{ width: 150 }}>Vigencia</th>
            <th className="td-center" style={{ width: 100 }}>
              Monto
            </th>
            <th className="td-center" style={{ width: 70 }}>
              % Com.
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Estado
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr
              key={c.contrato_id}
              className={selected?.contrato_id === c.contrato_id ? "sel" : ""}
              onClick={() => seleccionar(c)}
            >
              <td className="td-mono">{c.numero_contrato}</td>
              <td className="td-main">{c.nombre_contrato}</td>
              <td className="td-2">{c.anunciante_nombre ?? "—"}</td>
              <td className="td-mono" style={{ fontSize: 11 }}>
                {c.fecha_inicio_contrato} → {c.fecha_fin_contrato}
              </td>
              <td className="td-mono" style={{ textAlign: "right" }}>
                {fmtMonto(c.monto_contrato)}
              </td>
              <td className="td-center td-mono">{fmtPct(c.porcentaje_comision_contrato)}</td>
              <td className="td-center">
                <span className={`badge ${ESTADO_BADGE[c.estado_contrato]}`}>
                  {c.estado_contrato}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando contratos…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los contratos.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay contratos para los filtros seleccionados.</div>
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
          <div className="cat-title">Contratos</div>
          <div className="cat-sub">
            Contratos comerciales con los anunciantes: vigencia, monto y comisión específica que
            sobreescribe el default de la agencia.
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
            + Nuevo contrato
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar número o nombre…"
        filterLabel="Estado"
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
