/** Formulario INLINE de contacto (dentro del detalle del anunciante), mismo patrón que
 * `MarcaInlineForm`. El anunciante_id lo fija la pantalla.
 *
 * Fix: la raíz es un `<div>`, NO un `<form>`. Desde ADR-092 esta pieza también se monta
 * DENTRO del `<form>` de alta/edición de Anunciante (`ContactosSection` dentro de
 * `AnuncianteForm`) — un `<form>` anidado dentro de otro no es HTML válido: el navegador
 * lo aplana, así que el botón "Guardar" terminaba disparando el `submit` del formulario
 * EXTERIOR (el del anunciante), no el de este contacto. `handleSubmit` de react-hook-form
 * no necesita un evento de `<form>`: se puede invocar directo desde el `onClick` del
 * botón (mismo patrón recomendado por la librería para este caso).
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay } from "@/shared/ui";

const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const schema = z.object({
  nombre_contacto: z.string().trim().min(1, "El nombre del contacto es obligatorio.").max(160),
  puesto_contacto: z.string().trim().max(160).optional(),
  telefono_contacto: z.string().trim().max(40).optional(),
  email_contacto: z
    .string()
    .trim()
    .max(160)
    .refine((v) => v === "" || EMAIL_REGEX.test(v), "Correo inválido.")
    .optional(),
});

type ContactoFormValues = z.infer<typeof schema>;

export interface ContactoFormData {
  nombre_contacto: string;
  puesto_contacto?: string | null;
  telefono_contacto?: string | null;
  email_contacto?: string | null;
}

interface ContactoInlineFormProps {
  title: string;
  defaultValues?: Partial<ContactoFormValues>;
  submitting?: boolean;
  onSubmit: (data: ContactoFormData) => void;
  onCancel: () => void;
}

export function ContactoInlineForm({
  title,
  defaultValues,
  submitting,
  onSubmit,
  onCancel,
}: ContactoInlineFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ContactoFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre_contacto: "",
      puesto_contacto: "",
      telefono_contacto: "",
      email_contacto: "",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) =>
    onSubmit({
      nombre_contacto: data.nombre_contacto.trim(),
      puesto_contacto: data.puesto_contacto?.trim() || null,
      telefono_contacto: data.telefono_contacto?.trim() || null,
      email_contacto: data.email_contacto?.trim() || null,
    }),
  );

  return (
    <div
      className="inline-form"
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          void submit();
        }
      }}
    >
      <SavingOverlay visible={submitting} />
      <div className="if-title">{title}</div>

      <div className="fl fl-required">Nombre</div>
      <input className="fi" autoFocus placeholder="Ej. Ana López" {...register("nombre_contacto")} />
      <div className="fe">{errors.nombre_contacto?.message}</div>

      <div className="fl">Puesto o cargo</div>
      <input
        className="fi"
        placeholder="Ej. Gerente de Marketing"
        {...register("puesto_contacto")}
      />

      <div className="r2">
        <div>
          <div className="fl">Teléfono</div>
          <input className="fi" {...register("telefono_contacto")} />
        </div>
        <div>
          <div className="fl">Correo</div>
          <input className="fi" type="email" {...register("email_contacto")} />
          <div className="fe">{errors.email_contacto?.message}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 6 }}>
        <button type="button" className="btn btn-xs" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-xs btn-teal"
          disabled={submitting}
          onClick={() => void submit()}
        >
          {submitting ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </div>
  );
}
