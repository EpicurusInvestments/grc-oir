# Módulo F0-03 — Catálogos comerciales (Agencia · Anunciante · Marca · Contrato) · Fase: F0

> Cadena comercial encadenada. Es el módulo de F0 con más reglas: incluye **parámetros
> sensibles** (porcentajes de comisión y días de crédito) que exigen permiso por campo
> y registro en bitácora. Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupos
> "agencia", "anunciante", "contrato"; Marca se gestiona dentro de Anunciante).

## Propósito

Gestionar a los clientes comerciales (anunciantes), las agencias que los representan,
sus marcas y sus contratos. Es la base de la captura de órdenes (F1) y de la facturación.

## Entidades (spec BD v2)

### Agencia (10 campos)
`agencia_id` (PK), `nombre_agencia` (NOT NULL, único), `rfc_agencia` (NOT NULL, 13),
`contacto_nombre`, `contacto_email`, `contacto_telefono`,
**`porcentaje_comision_agencia_default` (DECIMAL · PARÁMETRO SENSIBLE)**, `activo`,
`created_at`, `updated_at`. No accede al sistema.

### Anunciante (14 campos)
`anunciante_id` (PK), `agencia_id` (FK NULL — null si trata directo), `nombre_comercial`
(NOT NULL), `nombre_fiscal` (NOT NULL — el que aparece en la factura), `rfc_anunciante`
(NOT NULL, 13), `localizacion`, `referencia_anunciante`, `contacto_nombre`,
`contacto_email`, `contacto_telefono`, **`dias_credito_default` (INTEGER · editable por
Ventas/CxC)**, `activo`, `created_at`, `updated_at`.

### Marca (5 campos)
`marca_id` (PK), `anunciante_id` (FK), `nombre_marca` (NOT NULL), `activo`, `created_at`.
- **Sin pantalla propia (confirmado):** Marca se gestiona **anidada dentro de Anunciante**
  (sub-lista en el detalle del anunciante: agregar/editar/desactivar marcas ahí mismo).

### Contrato (16 campos)
`contrato_id` (PK), `anunciante_id` (FK NOT NULL), `numero_contrato` (NOT NULL),
`nombre_contrato` (NOT NULL), `fecha_inicio_contrato` (NOT NULL), `fecha_fin_contrato`
(NOT NULL, ≥ inicio), `monto_contrato` (DECIMAL), **`porcentaje_comision_contrato`
(DECIMAL · sobreescribe el default de la agencia)**, `condiciones_comerciales` (TEXT),
`estado_contrato` (ENUM: vigente│suspendido│finalizado│cancelado), `archivo_contrato_path`,
`observaciones_contrato`, `activo`, `created_by`, `created_at`, `updated_at`.

## Parámetros sensibles (clave de este módulo)

Los campos `porcentaje_comision_agencia_default`, `porcentaje_comision_contrato` y
`dias_credito_default` son sensibles. Reglas (spec + pantalla):
- Antes de modificarlos: `field_permissions.verificar(...)`. **Por ahora solo Admin (IT)
  puede modificar estos campos** (decisión confirmada; más adelante se podrá abrir % a
  Dirección y días de crédito a Ventas/CxC).
- Al modificarlos: registro automático en `LogCambioParametro` (usuario, fecha, valor
  anterior, valor nuevo, ip). La pantalla pide **"Motivo del cambio (requerido si se
  modifica %)"** → capturar `motivo_cambio`.
- En la UI estos campos llevan tag «Audit log».

## Estados
- Agencia/Anunciante/Marca: `activo` (lógica).
- Contrato: `estado_contrato` (vigente → suspendido/finalizado/cancelado). Definir
  transiciones permitidas en el servicio. `[[POR LLENAR: confirmar transiciones — propuesta:
  vigente↔suspendido, vigente→finalizado, cualquiera→cancelado]]`

## Pantallas (de la pantalla F0)
- Agencia: lista + detalle; filtros Activas/Inactivas/Todas; campo % comisión con
  motivo de cambio. Botones `+ Nueva agencia`, `Crear agencia`, `Editar agencia`.
- Anunciante: lista + detalle; filtro extra **Vía agencia / Directo (Sin agencia)**;
  muestra cuántas marcas/contratos tiene. **Marca se administra anidada** en el detalle
  del anunciante.
- Contrato: lista + detalle; filtros Vigentes/Expiradas; adjuntar PDFs del contrato.
- Paginación por página en todas las listas.

## Roles / permisos (matriz RBAC)
- **Captura/edición: solo Admin (IT)** por ahora (incluidos los campos sensibles).
  Lectura: Facturación, CxC, Dirección, etc.

## Reglas de negocio clave
- RFC válido (13) y `nombre_agencia` único.
- `nombre_fiscal` del anunciante es el que va en la factura (puede diferir del comercial).
- `porcentaje_comision_contrato` sobreescribe el default de la agencia cuando existe.
- `fecha_fin_contrato >= fecha_inicio_contrato`.
- Adjuntos de contrato: ver Integraciones (S3).

## Integraciones — almacenamiento de adjuntos de contrato (S3)

- Los contratos tienen **varios documentos PDF** (documentación legal del contrato).
- **Estructura en S3:** directorio raíz `contratos/`, y dentro un directorio por
  contrato **cuyo nombre es el `numero_contrato`** → `contratos/<numero_contrato>/<archivo>.pdf`.
- **Nota de modelo:** la spec define `archivo_contrato_path` (singular), pero un contrato
  tiene N archivos. Decisión: `archivo_contrato_path` guarda el **prefijo/carpeta** del
  contrato en S3 (`contratos/<numero_contrato>/`); la lista de PDFs se obtiene listando
  ese prefijo. Si más adelante se requiere metadata por archivo (nombre, fecha, quién lo
  subió), se evaluará una tabla `ContratoDocumento` (1:N). `[[POR LLENAR: confirmar si se
  necesita esa tabla de documentos o basta con listar el prefijo de S3]]`
- Validar tipo (PDF) y tamaño al subir. Credenciales/bucket de S3 por configuración
  (`.env` / AWS Secrets Manager), nunca en el código. `[[POR LLENAR: nombre del bucket S3]]`

## Dependencias
- F0-00 (fundamentos) y los hooks de permiso por campo + auditoría de `core/`.

## Pendientes / dudas
- (Resuelto) Marca → solo anidada en Anunciante, sin pantalla propia.
- (Resuelto) Campos sensibles → por ahora solo Admin (IT) los modifica.
- (Resuelto) Adjuntos → varios PDF en S3 `contratos/<numero_contrato>/`.
- (Abierto) Transiciones de `estado_contrato` (propuesta arriba, confirmar).
- (Abierto) ¿Tabla `ContratoDocumento` (1:N) o basta listar el prefijo S3? Nombre del bucket.
