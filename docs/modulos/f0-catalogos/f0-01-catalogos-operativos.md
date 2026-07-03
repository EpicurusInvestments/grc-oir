# Módulo F0-01 — Catálogos operativos (Plaza · Afiliado · Estación) · Fase: F0

> Núcleo operativo de la transmisión. Tres entidades encadenadas con inferencia
> automática. Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupos "plaza",
> "afiliado"; estación se infiere desde afiliado/plaza).

## Propósito

Gestionar dónde y a través de quién se transmite: plazas geográficas, afiliados
(empresas que operan estaciones) y estaciones. Es prerrequisito de Tarifas (F0-02) y de
Órdenes (F1).

## Entidades (spec BD v2)

> **Estado: IMPLEMENTADO** (backend + migración aplicada a RDS + frontend). Migración
> Alembic `7300e6f940a3`. Ver `docs/API-CONTRACT.md` para los endpoints.

> **Nota de unificación (E-3):** aunque la spec lista `created_at` como único timestamp de
> Plaza y Estación, se agregó `updated_at` a **las tres** entidades para cumplir la
> convención "updated_at en toda entidad" de `CLAUDE.md §6`. Desviación consciente y
> uniforme respecto a la enumeración de la spec.

### Plaza
`plaza_id` (PK, `UNIQUEIDENTIFIER`), `nombre_plaza` (NOT NULL), `estado`, `activo`,
`created_at`, `updated_at`.

### Afiliado
`afiliado_id` (PK), `nombre_afiliado` (NOT NULL), `razon_social_afiliado` (NOT NULL),
`rfc_afiliado` (NOT NULL, **único**), `plaza_id` (FK **NOT NULL** — decisión E-1),
`contacto_nombre`, `contacto_email`, `contacto_telefono`, `activo`, `created_at`,
`updated_at`. No accede al sistema.
- La `plaza_id` del afiliado es la plaza en la que opera. La estación la hereda (ver abajo).
- **RFC:** se valida el formato oficial mexicano de **12-13 caracteres** (12 = persona
  moral, que es el caso típico de un afiliado; 13 = física), no exactamente 13. Se
  normaliza a mayúsculas. La columna es `NVARCHAR(13)` con índice UNIQUE.

### Estacion (1 campo de la spec omitido — ver nota)
`estacion_id` (PK), `afiliado_id` (FK NOT NULL), `plaza_id` (FK NOT NULL, **derivada** del
afiliado), `nombre_estacion` (NOT NULL), `frecuencia`, `tipo_senal` (ENUM `fm│am│tv`, como
`VARCHAR` + CHECK `ck_estacion_tipo_senal`), `activo`, `created_at`, `updated_at`.
- **Campo omitido:** `venta_directa_carmen_aristegui_cdmx` (BIT) de la spec se **omite
  deliberadamente** (decisión del equipo). Registrado como desviación en
  `docs/arquitectura.md` (ADR-006) para que no se reincorpore por error.
- **Regla de inferencia (spec + pantalla):** al seleccionar una estación se infieren
  automáticamente plaza, afiliado y razón social del afiliado.

## Regla de plaza de la estación — OPCIÓN A (CONFIRMADA)

La estación **hereda la plaza de su afiliado**. Implicaciones de diseño:
- En el **formulario** de estación NO se captura la plaza: al elegir el afiliado, la
  plaza se llena automáticamente (solo lectura) desde `Afiliado.plaza_id`.
- En el **servicio**, al crear/editar una estación, `Estacion.plaza_id` se asigna
  siempre = `Afiliado.plaza_id` (no se confía en un valor enviado por el cliente).
- Se asume que **un afiliado opera en una sola plaza**. Si en el futuro un afiliado
  necesita operar en varias plazas, se revisará esta regla (pasar a captura libre) en
  el momento correspondiente; el equipo lo indicará.
- Consecuencia: si se cambia la plaza de un afiliado, sus estaciones deben reflejar el
  cambio (la plaza se resuelve vía afiliado, así que se mantiene consistente por diseño).

## Estados y transiciones
- Estos catálogos solo manejan `activo` (alta lógica/baja lógica). Sin máquina de estados.

## Pantallas (implementadas, patrón lista + detalle)
- **Plaza** (`plaza`) y **Afiliados y estaciones** (`afiliado`) son dos entradas del grupo
  "Operación" del explorador. La **Estación NO tiene entrada propia**: se administra
  **anidada** dentro del detalle del afiliado (lista de estaciones + form inline).
- Ambas con filtros Activos/Inactivos/Todos, búsqueda y paginación por página.
- **Columnas de lista (1:1 con la pantalla aprobada):**
  - Plazas: Plaza · Estado · Estaciones · Estatus.
  - Afiliados: Afiliado (nombre + razón social) · Plaza principal · RFC · Estaciones · Estatus.
  - `Estaciones` (conteo) y `Plaza principal` (nombre) son **datos derivados** que el
    backend calcula por lote (sin N+1) y expone como `estaciones_count` / `plaza_nombre`
    (solo lectura). El conteo incluye estaciones inactivas (mismo criterio en ambas listas).
- Formularios con React Hook Form + Zod (validaciones espejo del backend).
- **Estación (inline):** al agregar/editar, la plaza se muestra de solo lectura con el tag
  «Heredado» (viene del afiliado) junto con su razón social; se captura nombre/clave,
  frecuencia y tipo de señal (FM/AM/TV).
- Baja con dependientes: cuando el backend responde 409, la UI muestra un diálogo de
  confirmación y reintenta con `forzar`.
- Botones `+ Nueva plaza`, `+ Nuevo afiliado`, `+ Agregar` (estación), `Editar`,
  `Activar/Desactivar`. Acciones de escritura visibles solo para admin (el backend valida).

## Roles / permisos
- **Captura: solo Admin (IT)** por ahora. En una **versión posterior**, Ventas también
  podrá capturar y editar afiliados/estaciones (cuando se habilite, ajustar RBAC).
- Lectura: demás áreas.

## Reglas de negocio clave (implementadas en la capa de servicio)
- `rfc_afiliado`: formato RFC MX de 12-13 caracteres (ver nota arriba), único (índice
  UNIQUE + verificación en servicio → 409 `conflicto` con mensaje claro).
- Estación obliga `afiliado_id`; `plaza_id` se hereda del afiliado (Opción A, ADR-005): el
  servicio la asigna = `Afiliado.plaza_id` y NO se captura en el formulario. Si cambia el
  afiliado en una edición, se recalcula.
- Baja lógica con confirmación (E-2): **no se puede desactivar**
  - una **plaza** con afiliados activos **o** estaciones activas, ni
  - un **afiliado** con estaciones activas,
  sin confirmar. El servicio responde 409 `dependencias_activas` (con el conteo en
  `detalles`) y el cliente reintenta con `forzar=true`. Mecanismo aditivo en la base
  (`CambioEstadoIn.forzar`, hook `_pre_desactivar`). La estación no tiene dependientes, su
  baja es directa.

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos). Plaza antes que Afiliado antes que Estación.

## Pendientes / dudas
- (Resuelto) Plaza de la estación → Opción A: hereda del afiliado (ADR-005).
- (Resuelto) Campo `venta_directa_carmen_aristegui_cdmx` → omitido (ADR-006).
- (Resuelto) Desactivar con dependientes → advertir antes de proceder (E-2; alcance de
  Plaza ampliado a afiliados activos O estaciones activas).
- (Resuelto) `afiliado.plaza_id` → NOT NULL (E-1), requerido por la herencia de plaza.
- (Resuelto) `updated_at` → agregado a las tres entidades (E-3, ver nota arriba).
- (Aclaración) `rfc_afiliado` → 12-13 caracteres (no exactamente 13): 12 para personas
  morales, que es el caso de los afiliados. Confirmar con el equipo si algún afiliado
  pudiera ser persona física (13).
