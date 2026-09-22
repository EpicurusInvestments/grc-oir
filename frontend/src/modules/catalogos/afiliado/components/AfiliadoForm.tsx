/** Formulario de alta/edición de Afiliado (React Hook Form + Zod). Refleja las
 * validaciones del backend: nombre y razón social requeridos, RFC MX (12-13, único —
 * la unicidad la valida el backend).
 *
 * Sin campo Plaza (ADR-096, petición del usuario): la plaza es una propiedad de la
 * Estación, no del Afiliado — se captura en la pantalla "Estaciones", no aquí.
 *
 * El contacto plano (`contacto_nombre`/`contacto_email`/`contacto_telefono`) ya NO se
 * captura aquí (ADR-094, mismo criterio que Anunciante/Agencia — ADR-091/092): queda de
 * solo lectura en el detalle si una fila vieja lo trae. "Contactos" (varios, sección
 * `ContactosSection`) es el reemplazo — en alta se capturan en memoria y se crean junto
 * con el afiliado; en edición, en vivo contra el backend.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay } from "@/shared/ui";

import type { AfiliadoCreate } from "../types";
import type { ContactoFormData } from "./ContactoInlineForm";
import { ContactosSection } from "./ContactosSection";

const RFC_REGEX = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/i;

const schema = z.object({
  nombre_afiliado: z.string().trim().min(1, "El nombre es obligatorio.").max(160),
  razon_social_afiliado: z.string().trim().min(1, "La razón social es obligatoria.").max(200),
  rfc_afiliado: z
    .string()
    .trim()
    .regex(
      RFC_REGEX,
      "RFC inválido: 3-4 letras + 6 dígitos (fecha AAMMDD) + 3 alfanuméricos (homoclave).",
    ),
});

type AfiliadoFormValues = z.infer<typeof schema>;

interface AfiliadoFormProps {
  title: string;
  /** Presente SOLO en edición: habilita la sección "Contactos" en modo servidor. En alta
   *  (`undefined`/`null`) los contactos se capturan en memoria y se crean justo después
   *  de guardar el afiliado. */
  afiliadoId?: string | null;
  defaultValues?: Partial<AfiliadoFormValues>;
  isEdit?: boolean;
  submitting?: boolean;
  /** `contactosNuevos` solo trae algo en ALTA; en edición siempre llega vacío, porque ahí
   *  ya se sincronizan solos contra el backend. */
  onSubmit: (data: AfiliadoCreate, contactosNuevos: ContactoFormData[]) => void;
  onCancel: () => void;
}

export function AfiliadoForm({
  title,
  afiliadoId = null,
  defaultValues,
  isEdit = false,
  submitting,
  onSubmit,
  onCancel,
}: AfiliadoFormProps) {
  const [contactosNuevos, setContactosNuevos] = useState<ContactoFormData[]>([]);
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
      ...defaultValues,
    },
  });

  const submit = handleSubmit((data) => {
    onSubmit(
      {
        nombre_afiliado: data.nombre_afiliado,
        razon_social_afiliado: data.razon_social_afiliado,
        rfc_afiliado: data.rfc_afiliado.toUpperCase(),
      },
      contactosNuevos,
    );
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
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

        <div className="fl fl-required">RFC</div>
        <input
          className="fi"
          maxLength={13}
          style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
          {...register("rfc_afiliado")}
        />
        <div className="fe">{errors.rfc_afiliado?.message}</div>

        <ContactosSection
          afiliadoId={isEdit ? afiliadoId : null}
          canWrite
          contactosNuevos={contactosNuevos}
          onContactosNuevosChange={setContactosNuevos}
        />
      </div>
      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-teal" disabled={submitting}>
          {submitting ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </form>
  );
}
