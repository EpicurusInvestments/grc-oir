/** Constantes de adjuntos de Facturación — deben coincidir con
 * `EXTENSIONES_ADJUNTO_FACTURACION` de `backend/app/integrations/almacenamiento/documentos.py`
 * (las mismas extensiones que Órdenes, más `xml` para el CFDI del timbrador).
 */
export const EXTENSIONES_ADJUNTO_FACTURACION = [
  "pdf",
  "doc",
  "docx",
  "xls",
  "xlsx",
  "jpg",
  "jpeg",
  "png",
  "xml",
] as const;
export const ADJUNTO_FACTURACION_ACCEPT = EXTENSIONES_ADJUNTO_FACTURACION.map((ext) => `.${ext}`).join(",");

/** Debe coincidir con `settings.s3_max_pdf_bytes` (10 MB por default). */
export const ADJUNTO_FACTURACION_MAX_BYTES = 10 * 1024 * 1024;
