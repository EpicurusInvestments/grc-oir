/** Input de adjunto de Facturación (XML/PDF del CFDI timbrado): mismo patrón que
 * `ordenes/components/AdjuntoOrdenInput.tsx` (ADR-042) — subida real al backend
 * (S3/local vía `AlmacenamientoPort`). Un solo archivo por campo; uno nuevo reemplaza la
 * referencia anterior (no se borra el anterior en el almacenamiento, solo deja de estar
 * referenciado).
 *
 * A diferencia de `AdjuntoOrdenInput` (input nativo visible), aquí toda la caja punteada
 * es clickeable (`<label>` envolviendo un `<input type="file">` oculto) — mismo look que
 * "Cargar XML del CFDI"/"Cargar PDF de la factura" del prototipo aprobado, pero con
 * subida real en vez de una caja decorativa sin función (ADR-051).
 */

import { useRef, useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import {
  adjuntosFacturacionApi,
  nombreDeAdjuntoFacturacionRef,
  type TipoAdjuntoFacturacion,
} from "../../api";
import { ADJUNTO_FACTURACION_MAX_BYTES } from "../../constants";

// ADR-207 (petición del usuario, corrige un bug real): un nombre de archivo largo
// (p. ej. "factura_prueba_corregida.xml") desbordaba el `.dropzone` — el truncado por
// CSS (`text-overflow: ellipsis`) no alcanzaba a contenerlo dentro del grid de 2
// columnas (XML/PDF) y aparecía un scroll horizontal en todo el panel. En vez de
// depender del ancho disponible, se trunca el nombre a un largo FIJO: las primeras 5
// letras + "…" + la extensión — y se muestra el nombre completo en un tooltip nativo
// (`title`) al pasar el mouse.
function truncarNombreArchivo(nombre: string): string {
  const idx = nombre.lastIndexOf(".");
  const raiz = idx > 0 ? nombre.slice(0, idx) : nombre;
  // Sin el punto propio de la extensión: los "..." ya hacen de separador visual: con
  // los dos puntos juntos ("....xml") se veía raro.
  const extension = idx > 0 ? nombre.slice(idx + 1) : "";
  if (raiz.length <= 5) return nombre;
  return `${raiz.slice(0, 5)}...${extension}`;
}

interface AdjuntoFacturaInputProps {
  tipo: TipoAdjuntoFacturacion;
  /** Texto de la caja vacía, p.ej. "Cargar XML del CFDI". */
  placeholder: string;
  value: string | null | undefined;
  onChange: (ref: string) => void;
  disabled?: boolean;
}

export function AdjuntoFacturaInput({
  tipo,
  placeholder,
  value,
  onChange,
  disabled,
}: AdjuntoFacturaInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verError, setVerError] = useState<string | null>(null);

  // ADR-205 (petición del usuario, corrige un bug real): cada campo es XML o PDF del
  // CFDI, NUNCA ambos — pero el selector nativo de archivos (y la validación del
  // front) aceptaba las 9 extensiones de TODO el módulo de Facturación por igual
  // (`ADJUNTO_FACTURACION_ACCEPT`/`EXTENSIONES_ADJUNTO_FACTURACION`, pensadas para los
  // adjuntos de FacturaAfiliado/Agencia/Vendedor, que sí admiten varios formatos) — el
  // botón "Cargar XML del CFDI" dejaba elegir un PDF (o un DOCX, una imagen…) desde el
  // explorador de Windows. Ahora cada campo se acota a SU propia extensión según el
  // sufijo de `tipo` (todas las variantes de esta pantalla terminan en "_pdf"/"_xml").
  const esPdf = tipo.endsWith("_pdf");
  const extensionEsperada = esPdf ? "pdf" : "xml";

  const onElegir = async (archivo: File | undefined) => {
    setError(null);
    if (!archivo) return;

    // Validación en el front (UX inmediata): el backend SIEMPRE revalida extensión,
    // magic bytes y tamaño — esto no reemplaza esa validación, la anticipa.
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "";
    if (ext !== extensionEsperada) {
      setError(`Extensión no permitida. Usa: .${extensionEsperada}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (archivo.size > ADJUNTO_FACTURACION_MAX_BYTES) {
      setError(`El archivo excede el tamaño máximo permitido (${Math.round(ADJUNTO_FACTURACION_MAX_BYTES / 1024 / 1024)} MB).`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setSubiendo(true);
    try {
      const { ref } = await adjuntosFacturacionApi.subir(tipo, archivo);
      onChange(ref);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : "No se pudo subir el archivo.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDescargar = async () => {
    if (!value) return;
    setVerError(null);
    try {
      await adjuntosFacturacionApi.ver(value);
    } catch (e) {
      setVerError(e instanceof ApiRequestError ? e.message : "No se pudo descargar el documento.");
    }
  };

  // ADR-203 (petición del usuario): además de descargar, un PDF ya cargado se puede
  // VER en un visor (pestaña nueva, imprimible desde ahí) — mismo visor que los PDFs
  // de Órdenes. XML no tiene un visor equivalente con sentido (no es un documento
  // visual), así que el botón solo aparece para los tipos "_pdf" (`esPdf` de arriba).
  const onVer = async () => {
    if (!value) return;
    setVerError(null);
    try {
      await adjuntosFacturacionApi.verEnVisor(value);
    } catch (e) {
      setVerError(e instanceof ApiRequestError ? e.message : "No se pudo abrir el documento.");
    }
  };

  return (
    <div>
      <label className={`dropzone${value ? " has-file" : ""}`}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
          <path d="M7 2v6M4 5l3-3 3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
        {/* ADR-207: el nombre ya viene truncado a un largo FIJO (`truncarNombreArchivo`),
            no depende del ancho disponible — `minWidth: 0` sigue aquí como respaldo (por
            si el placeholder, sin truncar, fuera más largo que el espacio disponible) y
            el `title` da el nombre completo en un tooltip nativo al pasar el mouse. */}
        <span
          title={value ? nombreDeAdjuntoFacturacionRef(value) : undefined}
          style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}
        >
          {subiendo
            ? "Subiendo…"
            : value
              ? truncarNombreArchivo(nombreDeAdjuntoFacturacionRef(value))
              : placeholder}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept={`.${extensionEsperada}`}
          disabled={disabled || subiendo}
          onChange={(e) => void onElegir(e.target.files?.[0])}
        />
      </label>
      {!subiendo && value && (
        <>
          {esPdf && (
            <button type="button" className="btn btn-sm" onClick={() => void onVer()}>
              Ver
            </button>
          )}
          <button type="button" className="btn btn-sm" onClick={() => void onDescargar()}>
            Descargar
          </button>
        </>
      )}
      {error && <div className="fe">{error}</div>}
      {verError && <div className="fe">{verError}</div>}
    </div>
  );
}
