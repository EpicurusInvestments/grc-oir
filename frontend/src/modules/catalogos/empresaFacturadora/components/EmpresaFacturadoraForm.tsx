/** Formulario de alta/edición de EmpresaFacturadora (React Hook Form + Zod). Refleja el
 * backend: nombre requerido (≤200), RFC MX 12-13 (único — lo valida el backend) y el
 * domicilio estructurado con autocompletado por código postal (ADR-059). */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { DomicilioPostalInput, type DomicilioPostalValues, SavingOverlay } from "@/shared/ui";

import type { EmpresaFacturadoraCreate } from "../types";

const RFC_REGEX = /^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$/i;

const schema = z.object({
  nombre_empresa: z.string().trim().min(1, "El nombre es obligatorio.").max(200),
  rfc_empresa: z
    .string()
    .trim()
    .regex(
      RFC_REGEX,
      "RFC inválido: 3-4 letras + 6 dígitos (fecha AAMMDD) + 3 alfanuméricos (homoclave).",
    ),
  // `direccion_empresa` (legacy): ya no tiene input propio, ver el domicilio estructurado
  // de abajo. Se conserva en el schema para no perder lo ya capturado en registros viejos.
  direccion_empresa: z.string().trim().optional(),
  calle: z.string().trim().max(150).optional(),
  numero_exterior: z.string().trim().max(20).optional(),
  numero_interior: z.string().trim().max(20).optional(),
  colonia: z.string().trim().max(150).optional(),
  localidad: z.string().trim().max(150).optional(),
  referencia_domicilio: z.string().trim().max(250).optional(),
  municipio: z.string().trim().max(150).optional(),
  estado: z.string().trim().max(100).optional(),
  pais: z.string().trim().max(3).optional(),
  codigo_postal: z.string().trim().max(5).optional(),
});

type EmpresaFacturadoraFormValues = z.infer<typeof schema>;

interface EmpresaFacturadoraFormProps {
  title: string;
  defaultValues?: Partial<EmpresaFacturadoraFormValues>;
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: EmpresaFacturadoraCreate) => void;
  onCancel: () => void;
}

export function EmpresaFacturadoraForm({
  title,
  defaultValues,
  submitting,
  submitError,
  onSubmit,
  onCancel,
}: EmpresaFacturadoraFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<EmpresaFacturadoraFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre_empresa: "",
      rfc_empresa: "",
      direccion_empresa: "",
      calle: "",
      numero_exterior: "",
      numero_interior: "",
      colonia: "",
      localidad: "",
      referencia_domicilio: "",
      municipio: "",
      estado: "",
      pais: "MEX",
      codigo_postal: "",
      ...defaultValues,
    },
  });

  const domicilio: DomicilioPostalValues = {
    calle: watch("calle") ?? "",
    numero_exterior: watch("numero_exterior") ?? "",
    numero_interior: watch("numero_interior") ?? "",
    colonia: watch("colonia") ?? "",
    localidad: watch("localidad") ?? "",
    referencia_domicilio: watch("referencia_domicilio") ?? "",
    municipio: watch("municipio") ?? "",
    estado: watch("estado") ?? "",
    pais: watch("pais") ?? "",
    codigo_postal: watch("codigo_postal") ?? "",
  };
  const onDomicilioChange = (patch: Partial<DomicilioPostalValues>) => {
    for (const [campo, valor] of Object.entries(patch)) {
      setValue(campo as keyof DomicilioPostalValues, valor, { shouldDirty: true });
    }
  };

  const submit = handleSubmit((data) => {
    onSubmit({
      nombre_empresa: data.nombre_empresa.trim(),
      rfc_empresa: data.rfc_empresa.toUpperCase(),
      direccion_empresa: data.direccion_empresa?.trim() || null,
      calle: data.calle?.trim() || null,
      numero_exterior: data.numero_exterior?.trim() || null,
      numero_interior: data.numero_interior?.trim() || null,
      colonia: data.colonia?.trim() || null,
      localidad: data.localidad?.trim() || null,
      referencia_domicilio: data.referencia_domicilio?.trim() || null,
      municipio: data.municipio?.trim() || null,
      estado: data.estado?.trim() || null,
      pais: data.pais?.trim() || null,
      codigo_postal: data.codigo_postal?.trim() || null,
    });
  });

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <SavingOverlay visible={submitting} />
      <div className="dh">
        <div className="dh-name">{title}</div>
      </div>
      <div className="db">
        <div className="sec">Datos fiscales</div>

        <div className="fl fl-required">Nombre / Razón social</div>
        <input className="fi" autoFocus {...register("nombre_empresa")} />
        <div className="fe">{errors.nombre_empresa?.message}</div>

        <div className="fl fl-required">RFC</div>
        <input
          className="fi"
          maxLength={13}
          style={{ textTransform: "uppercase", fontFamily: "var(--mono)" }}
          {...register("rfc_empresa")}
        />
        <div className="fe">{errors.rfc_empresa?.message}</div>

        <div className="sec">Domicilio</div>
        <DomicilioPostalInput values={domicilio} onChange={onDomicilioChange} disabled={submitting} />
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
