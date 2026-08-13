/** Gestión de usuarios (F5-00) — lista + panel de detalle, patrón de F0.
 *
 * Solo Admin: la ruta ya está bajo `RequireArea(["admin"])`, y aun así el backend valida
 * el permiso `usuarios:*` en cada endpoint. Aquí el RBAC es únicamente UX.
 *
 * Guardarraíl anti-auto-bloqueo: el backend responde 400 si alguien intenta desactivarse o
 * cambiarse su propia área. La UI se adelanta —deshabilita el botón y el select, y explica
 * por qué— para que el usuario no choque contra un error evitable.
 */

import { useState } from "react";

import { useSession } from "@/modules/auth/sessionContext";
import { ApiRequestError } from "@/shared/lib/apiClient";
import type { ListParams } from "@/shared/types";
import {
  CatalogToolbar,
  ConfirmDialog,
  DetailEmpty,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { PasswordDialog } from "../components/PasswordDialog";
import { UsuarioForm } from "../components/UsuarioForm";
import { useUsuarios } from "../hooks";
import { etiquetaArea, type Area, type Usuario, type UsuarioCreate } from "../types";

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

const fecha = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("es-MX");
};

export function UsuariosPage() {
  const { usuario: enSesion } = useSession();
  const { useList, useCreate, useUpdate, useSetEstado, useEstablecerPassword } = useUsuarios();

  const [filtro, setFiltro] = useState<Filtro>("activos");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<Usuario | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [confirmarEstado, setConfirmarEstado] = useState(false);
  const [dialogoPassword, setDialogoPassword] = useState(false);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const params: ListParams = { page, size, activo: activoDeFiltro(filtro), q: q || undefined };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();
  const establecerPassword = useEstablecerPassword();

  /** ¿El registro seleccionado soy yo? De ahí cuelga el guardarraíl anti-auto-bloqueo. */
  const esYo = (u: Usuario): boolean =>
    enSesion?.usuario_id != null && enSesion.usuario_id === u.usuario_id;

  const reset = () => {
    setSelected(null);
    setModo("view");
    setSubmitError(null);
    setErrorAccion(null);
  };

  const seleccionar = (u: Usuario) => {
    setSelected(u);
    setModo("view");
    setSubmitError(null);
    setErrorAccion(null);
  };

  const mensajeDeError = (e: unknown): string => {
    if (
      e instanceof ApiRequestError &&
      ["conflicto", "validacion", "sin_permiso", "error_dominio"].includes(e.codigo)
    ) {
      return e.message;
    }
    throw e;
  };

  const onCrear = async (data: UsuarioCreate) => {
    setSubmitError(null);
    try {
      const nuevo = await crear.mutateAsync(data);
      setSelected(nuevo);
      setModo("view");
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const onActualizar = async (data: UsuarioCreate) => {
    if (!selected) return;
    setSubmitError(null);
    try {
      // Se arman los campos del perfil UNO POR UNO: así la contraseña no puede colarse en
      // el PUT ni por accidente (tiene su propio endpoint, con su propia confirmación).
      const perfil = {
        nombre_usuario: data.nombre_usuario,
        email: data.email,
        area: data.area,
        roles_adicionales: data.roles_adicionales,
      };
      const upd = await actualizar.mutateAsync({ id: selected.usuario_id, data: perfil });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      setSubmitError(mensajeDeError(e));
    }
  };

  const onCambiarEstado = async () => {
    if (!selected) return;
    setErrorAccion(null);
    try {
      const upd = await setEstado.mutateAsync({
        id: selected.usuario_id,
        activo: !selected.activo,
      });
      setSelected(upd);
      setConfirmarEstado(false);
    } catch (e) {
      setConfirmarEstado(false);
      setErrorAccion(mensajeDeError(e));
    }
  };

  const onEstablecerPassword = async (password: string) => {
    if (!selected) return;
    setErrorAccion(null);
    try {
      const upd = await establecerPassword.mutateAsync({ id: selected.usuario_id, password });
      setSelected(upd);
      setDialogoPassword(false);
    } catch (e) {
      setErrorAccion(mensajeDeError(e));
    }
  };

  // ── panel de detalle ────────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <UsuarioForm
        title="Nuevo usuario"
        modo="new"
        submitting={crear.isPending}
        submitError={submitError}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <UsuarioForm
        title={`Editar: ${selected.nombre_usuario}`}
        modo="edit"
        esUsuarioPropio={esYo(selected)}
        defaultValues={{
          nombre_usuario: selected.nombre_usuario,
          email: selected.email,
          area: selected.area as Area,
          roles_adicionales: selected.roles_adicionales ?? "",
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
    const yo = esYo(selected);
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">{selected.nombre_usuario}</div>
              <div className="dh-sub" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <StatusBadge activo={selected.activo} />
                {!selected.tiene_password && (
                  <span className="badge b-amber">Sin contraseña</span>
                )}
                {yo && <span className="badge b-blue">Tú</span>}
              </div>
            </div>
            <button type="button" className="btn btn-sm" onClick={() => setModo("edit")}>
              Editar
            </button>
          </div>
        </div>

        <div className="db">
          <div className="sec">Identidad</div>
          <div className="fl">Correo electrónico</div>
          <div className="fv mono">{selected.email}</div>

          <div className="fl">Área</div>
          <div className="fv">{etiquetaArea(selected.area)}</div>

          <div className="fl">Roles adicionales</div>
          <div className="fv muted">{oGuion(selected.roles_adicionales)}</div>

          <div className="sec">Acceso</div>
          <div className="fl">Estado de la contraseña</div>
          <div className="fv">
            {selected.tiene_password
              ? "Establecida — el usuario puede iniciar sesión."
              : "Sin establecer — el usuario no puede iniciar sesión."}
          </div>

          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              setErrorAccion(null);
              setDialogoPassword(true);
            }}
          >
            <i className="pi pi-key" aria-hidden="true" />
            {selected.tiene_password ? "Restablecer contraseña" : "Establecer contraseña"}
          </button>

          <div className="sec">Registro</div>
          <div className="fl">Dado de alta</div>
          <div className="fv muted">{fecha(selected.created_at)}</div>
        </div>

        <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
          {errorAccion && (
            <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
              {errorAccion}
            </div>
          )}
          <div>
            <button
              type="button"
              className={`btn btn-sm ${selected.activo ? "btn-danger" : ""}`}
              disabled={setEstado.isPending || (yo && selected.activo)}
              title={
                yo && selected.activo
                  ? "No puedes desactivar tu propio usuario: perderías el acceso."
                  : undefined
              }
              onClick={() => setConfirmarEstado(true)}
            >
              {selected.activo ? "Desactivar" : "Activar"}
            </button>
          </div>
        </div>
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona un usuario para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th style={{ width: "28%" }}>Usuario</th>
            <th>Correo</th>
            <th style={{ width: "20%" }}>Área</th>
            <th className="td-center" style={{ width: 130 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => (
            <tr
              key={u.usuario_id}
              className={selected?.usuario_id === u.usuario_id ? "sel" : ""}
              onClick={() => seleccionar(u)}
            >
              <td className="td-main">{u.nombre_usuario}</td>
              <td className="td-2">{u.email}</td>
              <td className="td-2">{etiquetaArea(u.area)}</td>
              <td className="td-center">
                <div style={{ display: "flex", gap: 4, justifyContent: "center", flexWrap: "wrap" }}>
                  <StatusBadge activo={u.activo} />
                  {!u.tiene_password && <span className="badge b-amber">Sin contraseña</span>}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando usuarios…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar los usuarios.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay usuarios para el filtro seleccionado.</div>
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
          <div className="cat-title">Usuarios</div>
          <div className="cat-sub">
            Quién entra al sistema y con qué área. El área determina los permisos en todos los
            módulos.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-phase"
          onClick={() => {
            setSelected(null);
            setModo("new");
            setSubmitError(null);
          }}
        >
          + Nuevo usuario
        </button>
      </div>

      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar por nombre o correo…"
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

      {selected && (
        <>
          <ConfirmDialog
            visible={confirmarEstado}
            title={selected.activo ? "Desactivar usuario" : "Activar usuario"}
            message={
              selected.activo
                ? `${selected.nombre_usuario} dejará de poder iniciar sesión, y su sesión actual se cerrará de inmediato.`
                : `${selected.nombre_usuario} volverá a poder iniciar sesión con su contraseña.`
            }
            confirmLabel={selected.activo ? "Desactivar" : "Activar"}
            danger={selected.activo}
            loading={setEstado.isPending}
            onConfirm={onCambiarEstado}
            onCancel={() => setConfirmarEstado(false)}
          />
          <PasswordDialog
            visible={dialogoPassword}
            nombreUsuario={selected.nombre_usuario}
            primeraVez={!selected.tiene_password}
            submitting={establecerPassword.isPending}
            submitError={errorAccion}
            onSubmit={onEstablecerPassword}
            onCancel={() => {
              setDialogoPassword(false);
              setErrorAccion(null);
            }}
          />
        </>
      )}
    </>
  );
}
