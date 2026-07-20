/** Pantalla "Constantes del sistema" (menú "Configuración"): catálogos SAT/timbrador.
 *
 * Lista con filtros por GRUPO en pills (cada una con su conteo, del endpoint /conteos) y
 * búsqueda por clave/descripción/grupo. Para el operador es de SOLO LECTURA (badge en el
 * encabezado); el alta/edición y la carga masiva CSV son solo del Admin. Los valores que
 * aparecen aquí alimentan las pantallas de Facturación (F2).
 */

import { useMemo, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator, StatusBadge } from "@/shared/ui";

import { ConstanteForm } from "../components/ConstanteForm";
import { ImportCsvDialog } from "../components/ImportCsvDialog";
import { useConstantes } from "../hooks";
import type {
  ConstanteSistema,
  ConstanteSistemaCreate,
  ConstantesListParams,
  GrupoConstante,
} from "../types";
import { GRUPO_DESC, GRUPO_LABEL, GRUPOS } from "../types";

type Modo = "view" | "new" | "edit";
type GrupoFiltro = "all" | GrupoConstante;

const oGuion = (v?: string | null): string => (v && v.trim() ? v : "—");

export function ConstantesSistemaPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useConteos, useCreate, useUpdate, useSetEstado } = useConstantes();

  const [grupo, setGrupo] = useState<GrupoFiltro>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<ConstanteSistema | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const params: ConstantesListParams = {
    page,
    size,
    q: q || undefined,
    grupo: grupo === "all" ? undefined : grupo,
  };
  const list = useList(params);
  const conteos = useConteos(false);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  const conteoPorGrupo = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of conteos.data ?? []) map.set(c.grupo, c.total);
    return map;
  }, [conteos.data]);
  const totalGeneral = useMemo(
    () => (conteos.data ?? []).reduce((acc, c) => acc + c.total, 0),
    [conteos.data],
  );

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
  };

  const seleccionar = (c: ConstanteSistema) => {
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

  const onCrear = async (data: ConstanteSistemaCreate) => {
    setSubmitError(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const onActualizar = async (data: ConstanteSistemaCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      // El backend solo acepta descripción y valor (grupo/clave son identidad natural).
      const upd = await actualizar.mutateAsync({
        id: selected.constante_sistema_id,
        data: { descripcion: data.descripcion, valor: data.valor },
      });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      manejarSubmitError(e);
    }
  };

  const cambiarEstado = async (c: ConstanteSistema, activo: boolean) => {
    const upd = await setEstado.mutateAsync({ id: c.constante_sistema_id, activo });
    setSelected(upd);
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <ConstanteForm
        title="Nueva constante"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <ConstanteForm
        title={`Editar: ${selected.clave}`}
        isEdit
        defaultValues={{
          grupo: selected.grupo,
          clave: selected.clave,
          descripcion: selected.descripcion,
          valor: selected.valor ?? "",
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
              <div className="dh-name mono">{selected.clave}</div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className="badge b-purple">{selected.grupo}</span>
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
          <div className="sec">{GRUPO_LABEL[selected.grupo]}</div>
          <div className="fl">Descripción</div>
          <div className="fv">{selected.descripcion}</div>
          <div className="fl">Valor configurable</div>
          <div className="fv mono muted">{oGuion(selected.valor)}</div>
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
    detail = <DetailEmpty message="Selecciona una constante para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: 130 }}>Grupo</th>
            <th style={{ width: 100 }}>Clave</th>
            <th>Descripción</th>
            <th style={{ width: 110 }}>Valor</th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr
              key={c.constante_sistema_id}
              className={selected?.constante_sistema_id === c.constante_sistema_id ? "sel" : ""}
              onClick={() => seleccionar(c)}
            >
              <td>
                <span className="badge b-purple">{c.grupo}</span>
              </td>
              <td className="td-mono">{c.clave}</td>
              <td className="td-2">{c.descripcion}</td>
              <td className="td-mono">{oGuion(c.valor)}</td>
              <td className="td-center">
                <StatusBadge activo={c.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando constantes…</div>}
      {list.isError && (
        <div className="state-msg error">No se pudieron cargar las constantes.</div>
      )}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay constantes para el filtro seleccionado.</div>
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
          <div className="cat-title">
            Constantes del sistema
            {!canWrite && (
              <span className="badge b-gray" style={{ marginLeft: 8, fontSize: 10 }}>
                Solo lectura
              </span>
            )}
          </div>
          <div className="cat-sub">
            Catálogos del SAT y configuración del timbrador externo usados por Facturación
            (Fase 2). La edición está restringida al administrador del sistema.
          </div>
        </div>
        {canWrite && (
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn" onClick={() => setImportOpen(true)}>
              Importar CSV
            </button>
            <button
              type="button"
              className="btn btn-phase"
              onClick={() => {
                setSelected(null);
                setModo("new");
                setSubmitError(null);
              }}
            >
              + Nueva constante
            </button>
          </div>
        )}
      </div>

      {/* Pills por grupo con su conteo (del endpoint /conteos). */}
      <div
        style={{
          display: "flex",
          gap: 6,
          flexWrap: "wrap",
          alignItems: "center",
          padding: "10px 22px",
          background: "var(--surface2)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <button
          type="button"
          className={`fp ${grupo === "all" ? "active" : ""}`}
          onClick={() => {
            setGrupo("all");
            setPage(1);
            reset();
          }}
        >
          Todas <span style={{ opacity: 0.6, marginLeft: 3 }}>{totalGeneral}</span>
        </button>
        {GRUPOS.map((g) => (
          <button
            type="button"
            key={g}
            className={`fp ${grupo === g ? "active" : ""}`}
            title={GRUPO_LABEL[g]}
            onClick={() => {
              setGrupo(g);
              setPage(1);
              reset();
            }}
          >
            {g} <span style={{ opacity: 0.6, marginLeft: 3 }}>{conteoPorGrupo.get(g) ?? 0}</span>
          </button>
        ))}
      </div>

      {/* Banner descriptivo del grupo activo. */}
      {grupo !== "all" && (
        <div
          style={{
            padding: "10px 22px",
            background: "var(--purple-bg)",
            borderBottom: "1px solid var(--border)",
            fontSize: 11.5,
            color: "var(--purple-text)",
            lineHeight: 1.5,
          }}
        >
          <strong>{GRUPO_LABEL[grupo]}</strong> · {GRUPO_DESC[grupo]}
        </div>
      )}

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar por clave, descripción o grupo…"
        count={list.data ? `${items.length} de ${list.data.total}` : undefined}
      />
      <ListDetailLayout list={listNode} detail={detail} />

      <ImportCsvDialog visible={importOpen} onClose={() => setImportOpen(false)} />
    </>
  );
}
