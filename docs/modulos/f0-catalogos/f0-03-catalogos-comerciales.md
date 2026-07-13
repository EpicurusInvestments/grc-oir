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

## Integraciones — almacenamiento de adjuntos de contrato (S3)
- **Subida real DIFERIDA** (ADR-020): se construyó el **puerto anti-corrupción**
  `integrations/almacenamiento/` con **adaptador local** que resuelve el prefijo
  `contratos/<numero_contrato>/` (guardado en `archivo_contrato_path`), pero **no sube ni
  lista** archivos reales. La UI muestra la sección de adjuntos como placeholder.
- Config `S3_BUCKET_CONTRATOS` / `AWS_REGION` en `.env.example` (sin valores); credenciales
  por el proveedor de AWS del entorno (Secrets Manager), nunca versionadas.
- **Sin tabla `ContratoDocumento`** por ahora (basta el prefijo; se reevaluará si se
  requiere metadata por archivo). La integración real de S3 será una tarea aparte.

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
- **ADR-020** — Puerto de almacenamiento con subida S3 diferida.
- **ADR-021** — Lectura acotada del historial de auditoría por entidad.

## Pendientes / dudas
- (Resuelto) Marca → solo anidada en Anunciante, sin pantalla propia.
- (Resuelto) Campos sensibles → por ahora solo Admin (IT) los modifica + auditoría.
- (Resuelto) Transiciones de `estado_contrato` (ADR-019).
- (Resuelto) Adjuntos → prefijo S3; sin tabla `ContratoDocumento`; subida diferida (ADR-020).
- (Abierto) **Nombre del bucket S3** (`S3_BUCKET_CONTRATOS`) e integración real de subida:
  tarea aparte posterior a F0-03. `[[POR LLENAR: nombre del bucket S3]]`
- (Abierto, futuro) Abrir edición de sensibles a Dirección / Ventas-CxC cuando F5 administre
  `PermisoCampo`.
