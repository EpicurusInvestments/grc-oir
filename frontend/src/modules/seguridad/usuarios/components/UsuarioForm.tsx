/** Formulario de alta/edición de Usuario (React Hook Form + Zod).
 *
 * La contraseña SOLO aparece en el alta, y opcional: cambiarla después es una acción
 * explícita con su propio endpoint (`/usuarios/{id}/password`), no un campo que se toca
 * de paso al guardar el perfil.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay } from "@/shared/ui";

import { AREAS, AREA_LABEL, type Area, type UsuarioCreate } from "../types";
import { passwordSchema } from "./passwordSchema";

const schema = z.object({
  nombre_usuario: z.string().trim().min(1, "El nombre es obligatorio.").max(160),
  email: z
    .string()
    .trim()
    .min(1, "El correo es obligatorio.")
    .max(160)
    .email("Correo no válido."),
  area: z.enum(AREAS, { errorMap: () => ({ message: "Selecciona un área." }) }),
  roles_adicionales: z.string().trim().max(400).optional(),
  // Vacío = no establecer contraseña ahora (el backend la acepta nula).
  password: z.union([z.literal(""), passwordSchema]).optional(),
});

type UsuarioFormValues = z.infer<typeof schema>;

interface UsuarioFormProps {
  title: string;
  modo: "new" | "edit";
  defaultValues?: Partial<UsuarioFormValues>;
  /** True cuando se edita el usuario CON EL QUE SE ESTÁ TRABAJANDO: el backend impide
   *  cambiarse la propia área (se perdería el acceso a la administración). */
  esUsuarioPropio?: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: UsuarioCreate) => void;
  onCancel: () => void;
}

export function UsuarioForm({
  title,
  modo,
  defaultValues,
  esUsuarioPropio = false,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: UsuarioFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<UsuarioFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre_usuario: "",
      email: "",
      area: "ventas",
      roles_adicionales: "",
      password: "",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_usuario: data.nombre_usuario.trim(),
      email: data.email.trim().toLowerCase(),
      area: data.area as Area,
      roles_adicionales: data.roles_adicionales?.trim() || null,
      ...(modo === "new" && data.password ? { password: data.password } : {}),
    });
  });

  return (
    <form
      onSubmit={submit}
      style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}
    >
      <SavingOverlay visible={submitting} />
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>

      <div className="db">
        <div className="sec">Datos del usuario</div>

        <label className="fl fl-required" htmlFor="usuario-nombre">
          Nombre de usuario
        </label>
        <input id="usuario-nombre" className="fi" autoFocus {...register("nombre_usuario")} />
        <div className="fe">{errors.nombre_usuario?.message}</div>

        <label className="fl fl-required" htmlFor="usuario-email">
          Correo electrónico
        </label>
        <input
          id="usuario-email"
          className="fi"
          type="email"
          autoComplete="off"
          {...register("email")}
        />
        <div className="fe">{errors.email?.message}</div>
        <div className="fl" style={{ marginTop: -4, marginBottom: 10 }}>
          Es la credencial con la que inicia sesión.
        </div>

        <label className="fl fl-required" htmlFor="usuario-area">
          Área
        </label>
        <select
          id="usuario-area"
          className="fsel"
          disabled={esUsuarioPropio}
          {...register("area")}
        >
          {AREAS.map((area) => (
            <option key={area} value={area}>
              {AREA_LABEL[area]}
            </option>
          ))}
        </select>
        <div className="fe">{errors.area?.message}</div>
        {esUsuarioPropio && (
          <div className="inherit-notice" style={{ marginBottom: 10 }}>
            No puedes cambiar tu propia área: perderías el acceso a la administración del
            sistema. Pídeselo a otro usuario del área Administración.
          </div>
        )}

        <label className="fl" htmlFor="usuario-roles">
          Roles adicionales
        </label>
        <input id="usuario-roles" className="fi" {...register("roles_adicionales")} />
        <div className="fe">{errors.roles_adicionales?.message}</div>

        {modo === "new" && (
          <>
            <div className="sec">Acceso</div>
            <label className="fl" htmlFor="usuario-password">
              Contraseña inicial (opcional)
            </label>
            <input
              id="usuario-password"
              className="fi"
              type="password"
              autoComplete="new-password"
              {...register("password")}
            />
            <div className="fe">{errors.password?.message}</div>
            <div className="fl" style={{ marginTop: -4 }}>
              Si la dejas vacía, el usuario se crea pero no podrá iniciar sesión hasta que
              se le establezca una.
            </div>
          </>
        )}
      </div>

      <div className="df" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {submitError && (
          <div className="state-msg error" style={{ margin: 0, textAlign: "left" }}>
            {submitError}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-sm btn-teal" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
}
