/** Formulario de alta/edición de Afiliado (React Hook Form + Zod). Refleja las
 * validaciones del backend: nombre y razón social requeridos, RFC MX (12-13, único —
 * la unicidad la valida el backend), plaza obligatoria.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { Plaza } from "@/modules/catalogos/plaza/types";

import type { AfiliadoCreate } from "../types";

const RFC_REGEX = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/i;
const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const schema = z.object({
  nombre_afiliado: z.string().trim().min(1, "El nombre es obligatorio.").max(160),
  razon_social_afiliado: z.string().trim().min(1, "La razón social es obligatoria.").max(200),
  rfc_afiliado: z
    .string()
    .trim()
    .regex(RFC_REGEX, "RFC inválido (formato mexicano de 12-13 caracteres)."),
  plaza_id: z.string().min(1, "Selecciona una plaza."),
  contacto_nombre: z.string().trim().max(160).optional(),
  contacto_email: z
    .string()
    .trim()
    .max(160)
    .refine((v) => v === "" || EMAIL_REGEX.test(v), "Correo inválido.")
    .optional(),
  contacto_telefono: z.string().trim().max(40).optional(),
});

type AfiliadoFormValues = z.infer<typeof schema>;

interface AfiliadoFormProps {
  title: string;
  plazas: Plaza[];
  defaultValues?: Partial<AfiliadoFormValues>;
  submitting?: boolean;
  onSubmit: (data: AfiliadoCreate) => void;
  onCancel: () => void;
}

export function AfiliadoForm({
  title,
  plazas,
  defaultValues,
  submitting,
  onSubmit,
  onCancel,
}: AfiliadoFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AfiliadoFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre_afiliado: "",
      razon_social_afiliado: "",
      rfc_afiliado: "",
      plaza_id: "",
      contacto_nombre: "",
      contacto_email: "",
      contacto_telefono: "",
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_afiliado: data.nombre_afiliado,
      razon_social_afiliado: data.razon_social_afiliado,
      rfc_afiliado: data.rfc_afiliado.toUpperCase(),
      plaza_id: data.plaza_id,
      contacto_nombre: data.contacto_nombre?.trim() || null,
      contacto_email: data.contacto_email?.trim() || null,
      contacto_telefono: data.contacto_telefono?.trim() || null,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Identificación</div>

        <div className="fl fl-required">Nombre del afiliado</div>
        <input className="fi" autoFocus {...register("nombre_afiliado")} />
        <div className="fe">{errors.nombre_afiliado?.message}</div>

        <div className="fl fl-required">Razón social</div>
        <input className="fi" {...register("razon_social_afiliado")} />
        <div className="fe">{errors.razon_social_afiliado?.message}</div>

        <div className="r2">
          <div>
            <div className="fl fl-required">RFC</div>
            <input
              className="fi"
              maxLength={13}
              style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
              {...register("rfc_afiliado")}
            />
            <div className="fe">{errors.rfc_afiliado?.message}</div>
          </div>
          <div>
            <div className="fl fl-required">Plaza</div>
            <select className="fsel" {...register("plaza_id")}>
              <option value="">Selecciona…</option>
              {plazas.map((p) => (
                <option key={p.plaza_id} value={p.plaza_id}>
                  {p.nombre_plaza}
                  {p.estado ? ` · ${p.estado}` : ""}
                </option>
              ))}
            </select>
            <div className="fe">{errors.plaza_id?.message}</div>
          </div>
        </div>

        <div className="sec">Contacto</div>
        <div className="fl">Nombre</div>
        <input className="fi" {...register("contacto_nombre")} />
        <div className="fe">{errors.contacto_nombre?.message}</div>

        <div className="fl">Correo</div>
        <input className="fi" {...register("contacto_email")} />
        <div className="fe">{errors.contacto_email?.message}</div>

        <div className="fl">Teléfono</div>
        <input className="fi" {...register("contacto_telefono")} />
        <div className="fe">{errors.contacto_telefono?.message}</div>
      </div>
      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-phase" disabled={submitting}>
          {submitting ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </form>
  );
}
