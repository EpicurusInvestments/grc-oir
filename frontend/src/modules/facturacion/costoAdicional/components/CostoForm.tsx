/** Alta de CostoAdicional (React Hook Form + Zod).
 *
 * `periodo_contable` se valida aquí como `YYYY-MM` con mes 01–12. El CHECK de la tabla
 * solo puede garantizar la FORMA (7 caracteres con guion en la quinta posición), porque
 * SQLite no soporta clases de caracteres en `LIKE` — ver ADR-045. Esta validación y la
 * del schema Pydantic son las que realmente exigen dígitos.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { SavingOverlay } from "@/shared/ui";

import { TIPOS_COSTO, TIPO_COSTO_LABEL, type CostoAdicionalCreate } from "../../types";

const schema = z.object({
  tipo_costo: z.enum(TIPOS_COSTO, { errorMap: () => ({ message: "Selecciona el tipo." }) }),
  descripcion_costo: z.string().trim().min(1, "La descripción es obligatoria.").max(300),
  periodo_contable: z
    .string()
    .regex(/^\d{4}-(0[1-9]|1[0-2])$/, "Usa el formato AAAA-MM (por ejemplo, 2026-02)."),
  monto_costo: z
    .string()
    .min(1, "El monto es obligatorio.")
    .refine((v) => !Number.isNaN(Number(v)) && Number(v) >= 0, "Debe ser un monto válido."),
});

type Valores = z.infer<typeof schema>;

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: CostoAdicionalCreate) => void;
  onCancel: () => void;
}

const periodoActual = () => new Date().toISOString().slice(0, 7);

export function CostoForm({ submitting, submitError, onSubmit, onCancel }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: { periodo_contable: periodoActual(), tipo_costo: "overhead" },
  });

  return (
    <form className="form" onSubmit={handleSubmit((v) => onSubmit(v as CostoAdicionalCreate))}>
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">Nuevo costo adicional</div>
        <div className="dh-sub">Sin orden asociada queda como costo general del área.</div>
      </div>

      <div className="fg">
        <label className="fl" htmlFor="tipo_costo">
          Tipo <span className="req">*</span>
        </label>
        <select id="tipo_costo" className="in" {...register("tipo_costo")}>
          {TIPOS_COSTO.map((t) => (
            <option key={t} value={t}>
              {TIPO_COSTO_LABEL[t]}
            </option>
          ))}
        </select>
        {errors.tipo_costo && <div className="fe">{errors.tipo_costo.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="descripcion_costo">
          Descripción <span className="req">*</span>
        </label>
        <input id="descripcion_costo" className="in" {...register("descripcion_costo")} />
        {errors.descripcion_costo && <div className="fe">{errors.descripcion_costo.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="periodo_contable">
          Periodo contable <span className="req">*</span>
        </label>
        <input
          id="periodo_contable"
          className="in mono"
          placeholder="AAAA-MM"
          {...register("periodo_contable")}
        />
        {errors.periodo_contable && <div className="fe">{errors.periodo_contable.message}</div>}
      </div>

      <div className="fg">
        <label className="fl" htmlFor="monto_costo">
          Monto <span className="req">*</span>
        </label>
        <input id="monto_costo" className="in" inputMode="decimal" {...register("monto_costo")} />
        {errors.monto_costo && <div className="fe">{errors.monto_costo.message}</div>}
      </div>

      {submitError && <div className="state-msg error">{submitError}</div>}

      <div className="fa">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-sm btn-primary" disabled={submitting}>
          Guardar
        </button>
      </div>
    </form>
  );
}
