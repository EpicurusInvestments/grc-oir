# Módulo F0-03 — Catálogos comerciales (Agencia · Anunciante · Marca · Contrato) · Fase: F0

> **Estado: IMPLEMENTADO** (back + front, aplicado y verificado contra RDS). Cadena
> comercial encadenada; es el módulo de F0 con más reglas: estrena los **parámetros
> sensibles** (porcentajes de comisión y días de crédito) con permiso por campo + bitácora
> `LogCambioParametro`, y la primera **máquina de estados** (contrato). Referencias: spec
> BD v2 y `Fase_0_-_Catalogos.html` (grupos "agencia", "anunciante", "contrato"; Marca se
> gestiona dentro de Anunciante).

## Propósito

Gestionar a los clientes comerciales (anunciantes), las agencias que los representan, sus
marcas y sus contratos. Es la base de la captura de órdenes (F1) y de la facturación.

## Entidades (spec BD v2)

### Agencia (10 campos)
`agencia_id` (PK), `nombre_agencia` (NOT NULL, **único, case-insensitive**), `rfc_agencia`
(NOT NULL, 12-13), `contacto_nombre`, `contacto_email`, `contacto_telefono`,
**`porcentaje_comision_agencia_default` (NUMERIC(5,2) · PARÁMETRO SENSIBLE)**, `activo`,
`created_at`, `updated_at`. No accede al sistema.

### Anunciante (14 campos)
`anunciante_id` (PK), `agencia_id` (FK NULL — null si trata directo), `nombre_comercial`
(NOT NULL), `nombre_fiscal` (NOT NULL — el que aparece en la factura), `rfc_anunciante`
(NOT NULL, 12-13), `localizacion`, `referencia_anunciante`, `contacto_nombre`,
`contacto_email`, `contacto_telefono`, **`dias_credito_default` (INTEGER · PARÁMETRO
SENSIBLE)**, `activo`, `created_at`, `updated_at`.

### Marca (5 campos + `updated_at`)
`marca_id` (PK), `anunciante_id` (FK NOT NULL), `nombre_marca` (NOT NULL), `activo`,
`created_at`, `updated_at`.
- **Sin pantalla propia (confirmado):** Marca se gestiona **anidada dentro de Anunciante**
  (sub-lista en el detalle del anunciante: agregar/editar/desactivar ahí mismo), igual que
  Estación dentro de Afiliado en F0-01.
- **`updated_at`** no está en la spec de Marca; se añadió por uniformidad (ADR-011).

### Contrato (16 campos)
`contrato_id` (PK), `anunciante_id` (FK NOT NULL), `numero_contrato` (NOT NULL),
`nombre_contrato` (NOT NULL), `fecha_inicio_contrato` (NOT NULL), `fecha_fin_contrato`
(NOT NULL, ≥ inicio), `monto_contrato` (NUMERIC(14,2), NULL), **`porcentaje_comision_contrato`
(NUMERIC(5,2), NULL · PARÁMETRO SENSIBLE · sobreescribe el default de la agencia)**,
`condiciones_comerciales` (NVARCHAR 4000), `estado_contrato` (ENUM:
vigente│suspendido│finalizado│cancelado), `archivo_contrato_path`, `observaciones_contrato`,
`activo`, `created_by`, `created_at`, `updated_at`.

## Parámetros sensibles (clave de este módulo)

Los tres campos sensibles (`porcentaje_comision_agencia_default`, `dias_credito_default`,
`porcentaje_comision_contrato`) comparten el mismo mecanismo, implementado una sola vez en
`core/` (ADR-016) y llamado desde el `_pre_create`/`_pre_update` de cada servicio vía
`audit.registrar_cambio_sensible(...)`:
- **Permiso por campo:** `field_permissions.verificar(...)`. **Por ahora solo Admin (IT)**
  puede modificarlos (decisión confirmada; a futuro se podría abrir % a Dirección y días de
  crédito a Ventas/CxC — solo cambiaría el cuerpo del hook, F5).
- **Bitácora:** registro automático en `LogCambioParametro` (entidad, entidad_id, campo,
  valor anterior/nuevo, usuario, fecha, ip, motivo), en la **misma transacción** que el
  cambio. El **alta** también audita (`anterior=null`); en Contrato solo si se captura un %
  (es opcional).
- **Motivo del cambio:** requerido **solo si el valor cambia** en edición (400 si falta).
- En la UI: componente compartido `SensitiveField` con tag «Audit log»; el campo "Motivo
  del cambio" aparece **solo al modificar** el valor sensible.
- **Consulta:** cada catálogo expone `GET /catalogos/<recurso>/{id}/historial` (lectura
  acotada por entidad, ADR-021); la administración completa de auditoría es de F5.

## Estados
- Agencia / Anunciante / Marca: `activo` (baja lógica), con bloqueo por dependientes.
- Contrato: **máquina de estados** `estado_contrato` (ADR-019), independiente de `activo`,
  con transiciones **confirmadas**:
  - `vigente → {suspendido, finalizado, cancelado}`
  - `suspendido → {vigente, cancelado}`
  - `finalizado → {cancelado}`
  - `cancelado → ∅` (terminal)
  - Se cambia por `POST /catalogos/contratos/{id}/estado-contrato`; transición inválida →
    409 `transicion_invalida`. La UI solo ofrece las transiciones válidas del estado actual.

## Dependencias entre entidades (baja lógica)
- **Agencia** con anunciantes activos → 409 `dependencias_activas` (salvo `forzar`).
- **Anunciante** con marcas o contratos activos → 409 `dependencias_activas` (salvo `forzar`).
- Marca y Contrato no tienen dependientes.

## Pantallas (implementadas, grupo "Comerciales")
- **Agencia**: lista (Agencia · RFC · Contacto · % comisión · Anunciantes · Estatus) +
  detalle. Filtros Activas/Inactivas/Todas. % comisión con tag «Audit log» y motivo. Panel:
  datos fiscales, contacto, **Anunciantes representados** e **Historial de cambios**.
- **Anunciante**: lista (Nombre comercial · Razón social · RFC · Agencia · Crédito ·
  Estatus) + detalle. Filtros Estatus + **Relación (Todas / Vía agencia / Sin agencia)**.
  Panel: identificación, contacto, días de crédito (sensible), **Marcas anidadas**
  (add/edit/desactivar inline), **Contratos** (lectura) e **Historial de cambios**.
- **Contrato**: lista (Número · Nombre · Anunciante · Vigencia · Monto · % Com. · Estado) +
  detalle. Filtros por estado (Todos / Vigentes / Finalizados). Panel: anunciante,
  vigencia+monto, % comisión (sensible), condiciones, observaciones, **adjuntos
  (placeholder S3 diferido)**, **máquina de estados** (botones de transición válidos) e
  **Historial de cambios**. Formulario con validación `fecha_fin ≥ fecha_inicio`.
- Paginación por página en todas las listas. Botones de escritura ocultos para no-admin
  (UX; el backend valida siempre).

## Roles / permisos (matriz RBAC)
- **Captura/edición: solo Admin (IT)** por ahora (incluidos los campos sensibles).
  Lectura: demás áreas (Facturación, CxC, Dirección, etc.). Config en `core/security.py`.

## Reglas de negocio clave
- RFC válido (12-13, formato MX; se reutiliza el regex de F0-01) para agencia y anunciante.
- `nombre_agencia` **único case-insensitive** (collation `CI_AS` de RDS + verificación con
  `LOWER()` en el servicio → 409 `conflicto`; ADR-017).
- `nombre_fiscal` del anunciante es el que va en la factura (puede diferir del comercial).
- `porcentaje_comision_contrato` sobreescribe el default de la agencia cuando tiene valor.
- `fecha_fin_contrato >= fecha_inicio_contrato` (schema y servicio).

## Integraciones — almacenamiento de adjuntos de contrato (local | S3)
- **Subida real IMPLEMENTADA** (ADR-027, implementa ADR-020): el **puerto anti-corrupción**
  `integrations/almacenamiento/` tiene dos adaptadores que cumplen la misma interfaz —
  `AlmacenamientoLocal` (filesystem, default para dev/pruebas) y `AlmacenamientoS3` (boto3,
  bucket privado real). La **selección es por `STORAGE_BACKEND=local|s3`**
  (`get_almacenamiento()`); el prefijo `contratos/<numero_contrato>/` se guarda en
  `archivo_contrato_path`.
- **Endpoints** (bajo `/catalogos/contratos/{id}/adjuntos`): listar/descargar = lectura,
  subir/borrar = escritura. Solo PDF (extensión + *magic bytes*), tamaño máx. configurable
  (`S3_MAX_PDF_BYTES`, default 10 MB). El bucket es **privado**: los PDF se sirven SIEMPRE por
  el backend (RBAC), nunca por URL pública; el nombre se sanea y el acceso queda acotado al
  prefijo del contrato (anti *path traversal*).
- Config `STORAGE_BACKEND` / `S3_BUCKET_CONTRATOS` / `AWS_REGION` / `S3_MAX_PDF_BYTES` en
  `.env.example`; **credenciales AWS por la cadena de proveedores del entorno** (boto3), nunca
  versionadas ni en `config.py`.
- **Sin tabla `ContratoDocumento`** (basta el prefijo). **Limitación conocida:** renombrar
  `numero_contrato` no mueve los PDF ya subidos en S3 (fuera de alcance). **Nombre repetido
  sobrescribe** (se puede cambiar a rechazar duplicados si el negocio lo pide).

## Migraciones (aplicadas a RDS `GRC-OIR`)
- `c4e7a1b93f20` — `log_cambio_parametro` + `agencia`.
- `d5b8c2a71f36` — `anunciante` + `marca`.
- `e7f2a9c14b58` — `contrato`.

## Dependencias
- F0-00 (fundamentos) y los hooks de permiso por campo + auditoría de `core/` (estrenados
  aquí). El módulo `contrato` referencia `anunciante`, y `anunciante` referencia `agencia`
  (imports perezosos para las referencias inversas, patrón Plaza↔Afiliado).

## Decisiones registradas (ADRs)
- **ADR-016** — `LogCambioParametro` persistida + mecanismo único de campo sensible en `core/`.
- **ADR-017** — Collation `CI_AS` de RDS (unicidad textual case-insensitive).
- **ADR-018** — Handler de validación serializa con `jsonable_encoder` (fix del 500 en RFC/fechas inválidos).
- **ADR-019** — Máquina de estados de Contrato con endpoint dedicado.
- **ADR-020** — Puerto de almacenamiento con subida S3 diferida (implementada por ADR-027).
- **ADR-021** — Lectura acotada del historial de auditoría por entidad.
- **ADR-027** — Integración REAL de S3: adaptador S3 + selección local/S3 por env + endpoints de adjuntos.

## Pendientes / dudas
- (Resuelto) Marca → solo anidada en Anunciante, sin pantalla propia.
- (Resuelto) Campos sensibles → por ahora solo Admin (IT) los modifica + auditoría.
- (Resuelto) Transiciones de `estado_contrato` (ADR-019).
- (Resuelto) Adjuntos → prefijo S3; sin tabla `ContratoDocumento` (ADR-020).
- (Resuelto) **Integración real de subida/descarga** → adaptador S3 + selección por
  `STORAGE_BACKEND`; bucket `s3-grc-oir-dev` (`us-west-2`), servido por el backend (ADR-027).
- (Abierto, futuro) Abrir edición de sensibles a Dirección / Ventas-CxC cuando F5 administre
  `PermisoCampo`.
