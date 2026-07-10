# Módulo F0-02 — Tarifas (TarifaPlaza) · Fase: F0

> Tarifas de referencia por plaza. Se aísla en su propio módulo por tener campo
> calculado y vigencias. Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupo
> "tarifa": campos Plaza, Estado, Tarifa bruta, Descuento, Tarifa neta «Calc», Desde, Hasta).

## Propósito

Mantener la tarifa sugerida por plaza, tipo de señal y duración de spot, usada como
valor sugerido al capturar órdenes (F1).

## Entidad (spec BD v2)

### TarifaPlaza (13 campos)
`tarifa_plaza_id` (PK), `plaza_id` (FK NOT NULL), `tipo_senal` (ENUM: fm│am│tv),
`duracion_spot` (ENUM: 20s│30s│60s│mencion), `tarifa_bruta` (DECIMAL),
`descuento_pct` (DECIMAL), **`tarifa_neta` (Calculado)**, `vigencia_desde` (DATE),
`vigencia_hasta` (DATE), `notas`, `activo`, `created_at`, `created_by`.

- **Campo calculado (fórmula de la spec):**
  `tarifa_neta = tarifa_bruta * (1 - descuento_pct / 100)`.
  Lo calcula el servicio; en el front se muestra de solo lectura con tag «Calc».

## Estados
- Solo `activo`. La pantalla además distingue tarifas **Vigentes / Expiradas** según
  `vigencia_hasta` vs la fecha actual (filtro derivado, no un campo de estado).

## Pantallas (de la pantalla F0)
- Lista + detalle con filtros (Todas / Vigentes / Expiradas / Activas / Inactivas) y
  paginación por página.
- Formulario: Plaza, Estado (de la plaza), Tipo de señal, Duración de spot, Tarifa bruta,
  Descuento, Tarifa neta (Calc, solo lectura), Desde, Hasta.

## Roles / permisos
- **Captura: solo Admin (IT)** por ahora (edita catálogos y fija tarifas). Lectura: demás.

## Reglas de negocio clave
- `tarifa_neta` nunca se acepta como entrada (es calculado por el servicio).
- `vigencia_hasta >= vigencia_desde`.
- **Validación de solapamiento (confirmada):** al cargar/editar una tarifa, el servicio
  debe validar que, para la misma combinación **plaza + tipo_senal + duracion_spot**, no
  exista otra tarifa **activa** cuya vigencia se solape con la nueva
  (`[vigencia_desde, vigencia_hasta]`). Si solapa, rechazar con error claro indicando la
  tarifa en conflicto.

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos) y F0-01 (Plaza debe existir).

## Estado de implementación (F0-02 entregada)

Implementado sobre la base de F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`).
Modelo, schemas, repositorio y servicio en `backend/app/modules/catalogos/tarifa.py`;
migración `20260708_1200-b73f13de1b80_f0_02_tarifas.py`; pantalla en
`frontend/src/modules/catalogos/tarifa/`. Endpoints en `docs/API-CONTRACT.md` (sección
Tarifas por plaza). Detalles de diseño en **ADR-015**.

**Decisiones tomadas al implementar (aprobadas por el equipo):**
- **E-1** — `vigencia_desde` y `vigencia_hasta` **obligatorias** (NOT NULL + CHECK
  `vigencia_hasta >= vigencia_desde`). El negocio no maneja tarifas abiertas/sin fin.
- **E-2** — `created_by` se guarda como **texto (username)**, no FK: la entidad `Usuario`
  llega en F0-04; se reevaluará migrar a FK entonces.
- **E-3** — El filtro Vigentes/Expiradas es **server-side** reemplazando SOLO la ruta
  `listar` de la factory dentro de `tarifa.py` (sin tocar `crud_router.py`).
- **E-4** — Los montos (`tarifa_bruta`, `descuento_pct`, `tarifa_neta`) viajan como
  **string** en el JSON para preservar la precisión `Decimal`.
- **E-5** — Lista con columnas de la pantalla aprobada (Plaza · Señal · Duración · Tarifa
  bruta · Desc · Tarifa neta · Vigencia) + columna **Estatus** (activo) para que los filtros
  Activas/Inactivas sean legibles. Chip **Vigente/Expirada** derivado en la vista.

**Reglas clave, dónde viven:**
- `tarifa_neta`: calculada con `Decimal` (`ROUND_HALF_UP`, 2 decimales) en el servicio y
  persistida; recalculada en cada edición; nunca aceptada del cliente.
- Solapamiento: consulta en el repositorio (intervalos cerrados, bordes inclusivos, solo
  contra tarifas activas de la misma combinación, excluyendo la propia al editar); se valida
  al crear, editar y **reactivar** → 409 `conflicto`.
- Filtro `?vigencia` con `hoy` fijado por el servidor (no por el cliente).

**Búsqueda (`q`):** abarca **nombre de plaza, estado de plaza y notas** (parcial,
case-insensitive, coincide en cualquiera). Como nombre/estado están en `plaza`, se resuelve
con un **único JOIN** a `plaza` en `TarifaRepository._apply_filters` (sin N+1, no duplica
filas por ser N:1); `ilike` es portable a SQL Server (`lower() LIKE lower()`).

**Portabilidad SQL Server:** comparaciones `activo == True` (→ `activo = 1`, ADR-014) y de
fechas contra parámetros; tests compilan el filtro de solapamiento y el JOIN de búsqueda con
el dialecto mssql. Pruebas de backend en `app/tests/test_f0_02_tarifas.py` (29 casos:
neta/redondeo, vigencia, solapamiento y bordes, reactivación, enums, filtros por
plaza/vigencia, búsqueda por plaza/estado/notas, enriquecimiento).

**Ajustes de integración con las pantallas aprobadas (dentro de F0-02):**
- **"Tarifas vigentes" en el panel de Plaza (F0-01):** al seleccionar una plaza, su panel de
  detalle lista las tarifas activas y no vencidas de esa plaza (formato `FM · 30s` /
  `$6,200.00 bruta · 5% desc.`). Se resuelve **reutilizando el listado** con el filtro nuevo
  `GET /catalogos/tarifas?plaza_id=…&activo=true&vigencia=vigente` (no se creó endpoint
  aparte). Hook `useTarifasVigentesPorPlaza` (deshabilitado sin plaza seleccionada;
  comparte prefijo de key `["tarifa"]`, así que se refresca al crear/editar tarifas).
- **Contadores del sidebar del explorador (F0-00):** el menú muestra el conteo real solo de
  los catálogos ya implementados (Plazas, Afiliados/estaciones, Tarifas por plaza),
  reutilizando el `total` del listado paginado (una consulta `size:1` por catálogo). Los
  catálogos aún no implementados (F0-03/04/05) siguen en 0 sin error.

## Pendientes / dudas
- (Resuelto) La tarifa es por **plaza + señal + duración** (no por estación).
- (Resuelto E-1..E-5) Ver "Estado de implementación".
