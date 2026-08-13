/** Diálogo para establecer / restablecer la contraseña de un usuario (F5-00).
 *
 * Acción explícita y separada de editar el perfil: cambiar una contraseña no debe ser un
 * efecto colateral de guardar un formulario. La contraseña se escribe dos veces para
 * atrapar erratas antes de dejar a alguien fuera del sistema.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { Dialog } from "primereact/dialog";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { MIN_CARACTERES, passwordSchema } from "./passwordSchema";

const schema = z
  .object({
    password: passwordSchema,
    confirmacion: z.string(),
  })
  .refine((datos) => datos.password === datos.confirmacion, {
    message: "Las contraseñas no coinciden.",
    path: ["confirmacion"],
  });

type PasswordFormValues = z.infer<typeof schema>;

interface PasswordDialogProps {
  visible: boolean;
  nombreUsuario: string;
  /** True si el usuario todavía no tiene contraseña (cambia el texto de la acción). */
  primeraVez: boolean;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}

export function PasswordDialog({
  visible,
  nombreUsuario,
  primeraVez,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: PasswordDialogProps) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PasswordFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirmacion: "" },
  });

  const cerrar = () => {
    reset();
    onCancel();
  };

  const enviar = handleSubmit((datos) => onSubmit(datos.password));

  return (
    <Dialog
      header={primeraVez ? "Establecer contraseña" : "Restablecer contraseña"}
      visible={visible}
      onHide={cerrar}
      style={{ width: 420 }}
    >
      <form onSubmit={enviar}>
        <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 14 }}>
          {primeraVez ? (
            <>
              <strong>{nombreUsuario}</strong> aún no puede iniciar sesión. Al establecer su
              contraseña quedará habilitado.
            </>
          ) : (
            <>
              La contraseña actual de <strong>{nombreUsuario}</strong> dejará de funcionar de
              inmediato. Comunícale la nueva por un canal seguro.
            </>
          )}
        </p>

        <label className="fl fl-required" htmlFor="password-nueva">
          Nueva contraseña
        </label>
        <input
          id="password-nueva"
          className="fi"
          type="password"
          autoComplete="new-password"
          autoFocus
          {...register("password")}
        />
        <div className="fe">{errors.password?.message}</div>

        <label className="fl fl-required" htmlFor="password-confirmacion">
          Confirmar contraseña
        </label>
        <input
          id="password-confirmacion"
          className="fi"
          type="password"
          autoComplete="new-password"
          {...register("confirmacion")}
        />
        <div className="fe">{errors.confirmacion?.message}</div>

        <div className="fl" style={{ marginTop: -4 }}>
          Mínimo {MIN_CARACTERES} caracteres.
        </div>

        {submitError && (
          <div className="state-msg error" style={{ margin: "10px 0 0", textAlign: "left" }}>
            {submitError}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <button type="button" className="btn btn-sm" onClick={cerrar} disabled={submitting}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-sm btn-phase" disabled={submitting}>
            {submitting ? "Guardando…" : "Guardar contraseña"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
