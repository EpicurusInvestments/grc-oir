# Módulo F0-01 — Catálogos operativos (Plaza · Afiliado · Estación) · Fase: F0

> Núcleo operativo de la transmisión. Tres entidades encadenadas con inferencia
> automática. Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupos "plaza",
> "afiliado"; estación se infiere desde afiliado/plaza).

## Propósito

Gestionar dónde y a través de quién se transmite: plazas geográficas, afiliados
(empresas que operan estaciones) y estaciones. Es prerrequisito de Tarifas (F0-02) y de
Órdenes (F1).

## Entidades (spec BD v2)

### Plaza (5 campos)
`plaza_id` (PK), `nombre_plaza` (NOT NULL), `estado`, `activo`, `created_at`.

### Afiliado (11 campos)
`afiliado_id` (PK), `nombre_afiliado` (NOT NULL), `razon_social_afiliado` (NOT NULL),
`rfc_afiliado` (NOT NULL, 13), `plaza_id` (FK), `contacto_nombre`, `contacto_email`,
`contacto_telefono`, `activo`, `created_at`, `updated_at`. No accede al sistema.
- La `plaza_id` del afiliado es la plaza en la que opera. La estación la hereda (ver abajo).

### Estacion (9 campos en spec; 1 omitido — ver nota)
`estacion_id` (PK), `afiliado_id` (FK NOT NULL), `plaza_id` (FK NOT NULL),
`nombre_estacion` (NOT NULL), `frecuencia`, `tipo_senal` (ENUM: fm│am│tv),
`activo`, `created_at`.
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

## Pantallas (de la pantalla F0)
- Lista + detalle por catálogo (Plaza, Afiliado), con filtros Activos/Inactivos/Todos
  y paginación por página.
- Estación: al capturar/seleccionar el afiliado, el formulario autocompleta plaza
  (solo lectura) y razón social del afiliado.
- Botones `+ Nueva plaza`, `+ Nuevo afiliado`, `Editar`, `Activar/Desactivar`.

## Roles / permisos
- **Captura: solo Admin (IT)** por ahora. En una **versión posterior**, Ventas también
  podrá capturar y editar afiliados/estaciones (cuando se habilite, ajustar RBAC).
- Lectura: demás áreas.

## Reglas de negocio clave
- `rfc_afiliado`: 13 caracteres, formato RFC válido, único.
- Estación obliga `afiliado_id`; `plaza_id` se hereda del afiliado (Opción A), no se
  captura manualmente.
- Baja lógica; **no permitir desactivar una plaza/afiliado que tenga estaciones activas
  dependientes sin antes advertir** al usuario (confirmar/forzar). Comportamiento confirmado.

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos). Plaza antes que Afiliado antes que Estación.

## Pendientes / dudas
- (Resuelto) Plaza de la estación → Opción A: hereda del afiliado.
- (Resuelto) Campo `venta_directa_carmen_aristegui_cdmx` → omitido (ADR-006).
- (Resuelto) Desactivar con dependientes → advertir antes de proceder.
