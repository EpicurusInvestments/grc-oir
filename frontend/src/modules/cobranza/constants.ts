/** Constantes de adjuntos de Cobranza y Pagos — deben coincidir con
 * `EXTENSIONES_ADJUNTO_ORDENES` de `backend/app/integrations/almacenamiento/documentos.py`
 * (el router de adjuntos de F3 no la sobrescribe: mismo default que F1, sin el XML que sí
 * acepta F2 para el CFDI).
 */
export const EXTENSIONES_ADJUNTO_COBRANZA = [
  "pdf",
  "jpg",
  "jpeg",
  "png",
  "docx",
  "xlsx",
  "doc",
  "xls",
] as const;
export const ADJUNTO_COBRANZA_ACCEPT = EXTENSIONES_ADJUNTO_COBRANZA.map((ext) => `.${ext}`).join(
  ",",
);

/** Debe coincidir con `settings.s3_max_pdf_bytes` (10 MB por default). */
export const ADJUNTO_COBRANZA_MAX_BYTES = 10 * 1024 * 1024;
