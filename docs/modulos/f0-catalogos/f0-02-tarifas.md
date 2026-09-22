# Módulo F0-02 — Tarifas (TarifaPlaza) · Fase: F0

> Tarifas de referencia por estación. Se aísla en su propio módulo por tener campo
> calculado. Referencias: spec BD v2 (diseño original, ver nota ADR-097 abajo) y
> `Fase_0_-_Catalogos.html` (grupo "tarifa").
>
> **ADR-097 (petición del usuario, 2026-09-21):** el diseño original de F0-02 (spec BD v2)
> era por **plaza** y con **vigencia**. Se reemplazó por completo: ahora es por
> **estación** ("Nombre de la emisora") + **producto** (campo nuevo), y ya NO tiene
> vigencia. Ver ADR-097 en `docs/arquitectura.md` para el detalle de la decisión.

## Propósito

Mantener la tarifa sugerida por estación, producto, tipo de señal y duración de spot,
usada como valor sugerido al capturar órdenes (F1).

## Entidad (post-ADR-097 — YA NO coincide con la spec BD v2 original)

### TarifaPlaza (12 campos)
`tarifa_plaza_id` (PK), `estacion_id` (FK NOT NULL a `Estacion`), `tipo_senal` (ENUM:
fm│am│tv), `duracion_spot` (ENUM: 20s│30s│60s — **sin `mencion`**, ADR-098),
**`producto`** (ENUM NUEVO, fuera de la spec: spot│mencion│control_remoto│patrocinio),
**`tarifa_bruta` (PARÁMETRO SENSIBLE, ADR-099)**, **`descuento_pct` (PARÁMETRO SENSIBLE,
ADR-099)**, **`tarifa_neta` (Calculado)**, `notas`, `activo`, `created_at`, `created_by`.
- **`duracion_spot` ya NO acepta `mencion` (ADR-098):** ese valor solo vive en
  `producto` desde ADR-097 — tenerlo también aquí era conceptualmente redundante (una
  "mención" no dura 20/30/60 segundos). El mismo cambio aplica a `OrdenCliente`/
  `OrdenEstacion` (F1), que comparten el enum `DuracionSpot` (ADR-032).

- **Campo calculado (fórmula de la spec, sin cambio):**
  `tarifa_neta = tarifa_bruta * (1 - descuento_pct / 100)`.
  Lo calcula el servicio; en el front se muestra de solo lectura con tag «Calc».
- **`estacion_id` reemplaza a `plaza_id` (ADR-097):** la tarifa ya no es "por plaza",
  es "por estación" — el formulario captura "Nombre de la emisora" (select de
  `Estacion`, ADR-094), no Plaza.
- **`producto` es NUEVO** (fuera de la spec BD v2): selector justo debajo de la emisora.
- **`vigencia_desde`/`vigencia_hasta` se ELIMINARON por completo** (ADR-097): el negocio
  ya no maneja tarifas con vigencia.
- **`tarifa_bruta`/`descuento_pct` son PARÁMETROS SENSIBLES (ADR-099, petición del
  usuario):** cada cambio se registra en `LogCambioParametro` (usuario, fecha, valor
  anterior, valor nuevo) — mismo mecanismo que Agencia/Vendedor/Contrato (ADR-016).

## Estados
- Solo `activo`. Ya NO hay filtro Vigentes/Expiradas (eliminado junto con la vigencia).

## Pantallas (de la pantalla F0, ajustada por ADR-097)
- Lista + detalle con filtros (Todas / Activas / Inactivas) y paginación por página.
- Formulario: Nombre de la emisora (select de Estación), Producto (select), Tipo de
  señal, Duración de spot, Tarifa bruta, Descuento, Tarifa neta (Calc, solo lectura).

## Roles / permisos
- **Captura: solo Admin (IT)** por ahora (edita catálogos y fija tarifas). Lectura: demás.
- **Permiso por campo (ADR-099):** `tarifa_bruta`/`descuento_pct` además pasan por
  `field_permissions.verificar` — hoy el mismo placeholder de F0 ("solo Admin"), listo
  para cuando llegue `PermisoCampo` (F5).

## Reglas de negocio clave
- `tarifa_neta` nunca se acepta como entrada (es calculado por el servicio).
- **Sin duplicado activo (ADR-097, reemplaza la validación de solapamiento por
  vigencia):** al crear/editar/reactivar una tarifa, el servicio valida que, para la
  misma combinación **estación + tipo_senal + duracion_spot + producto**, no exista otra
  tarifa **activa**. Si existe, rechaza con 409 `conflicto` indicando la tarifa en
  conflicto.
- **`tarifa_bruta`/`descuento_pct` como parámetros sensibles (ADR-099):** el alta audita
  ambos campos con `anterior=None` (sin exigir motivo — es la captura inicial); la
  edición exige `motivo_cambio` (transitorio, no es columna) SOLO si el valor
  efectivamente cambió, y audita cada campo que cambió por separado. Los dos campos
  comparten un único "Motivo del cambio" en la pantalla (mismo criterio que los 3 % de
  comisión de `OrdenCliente`, F1) — no uno por campo.

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos) y F0-01 (Estación debe existir — ADR-094).

## Estado de implementación (F0-02 entregada, restructurada por ADR-097)

Implementado sobre la base de F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`).
Modelo, schemas, repositorio y servicio en `backend/app/modules/catalogos/tarifa.py`;
migraciones `20260708_1200-b73f13de1b80_f0_02_tarifas.py` (original, por plaza + vigencia)
y `20260921_1500-96798afba3cc_f0_02_tarifa_por_estacion.py` (ADR-097: por estación +
producto, sin vigencia). **Sin migración propia para ADR-099** (parámetros sensibles): no
agrega columnas — reutiliza la tabla `log_cambio_parametro` ya existente (ADR-016).
Pantalla en `frontend/src/modules/catalogos/tarifa/`. Endpoints en `docs/API-CONTRACT.md`
(sección Tarifas). Detalles de diseño original en **ADR-015**; la restructuración de
Plaza→Estación en **ADR-097**; los parámetros sensibles en **ADR-099**.

**Decisiones tomadas al implementar originalmente (E-1..E-5, superadas por ADR-097 donde
se indica):**
- ~~E-1 — `vigencia_desde`/`vigencia_hasta` obligatorias~~ — **eliminado** (ADR-097).
- **E-2** — `created_by` se guarda como **texto (username)**, no FK: la entidad `Usuario`
  llega en F0-04; se reevaluará migrar a FK entonces. **Vigente.**
- ~~E-3 — filtro Vigentes/Expiradas server-side, ruta `listar` custom~~ — **eliminado**
  (ADR-097): sin vigencia no hay filtro que derivar, así que el CRUD genérico de
  `build_crud_router` alcanza sin overrides de router (la búsqueda `q` sigue viviendo en
  `TarifaRepository._apply_filters`, que no depende de la ruta).
- **E-4** — Los montos (`tarifa_bruta`, `descuento_pct`, `tarifa_neta`) viajan como
  **string** en el JSON para preservar la precisión `Decimal`. **Vigente.**
- **E-5** — Lista con columnas: Emisora · Producto · Señal · Duración · Tarifa bruta ·
  Desc · Tarifa neta · Estatus (ajustada por ADR-097: sin columna Vigencia).

**Reglas clave, dónde viven:**
- `tarifa_neta`: calculada con `Decimal` (`ROUND_HALF_UP`, 2 decimales) en el servicio y
  persistida; recalculada en cada edición; nunca aceptada del cliente.
- **Sin duplicado activo (ADR-097):** consulta en el repositorio (misma combinación
  estación+tipo_senal+duracion_spot+producto, solo contra tarifas activas, excluyendo la
  propia al editar); se valida al crear, editar y **reactivar** → 409 `conflicto`.

**Búsqueda (`q`):** abarca **nombre de estación, siglas de estación y notas** (parcial,
case-insensitive, coincide en cualquiera). Como nombre/siglas están en `estacion`, se
resuelve con un **único JOIN** a `estacion` en `TarifaRepository._apply_filters` (sin N+1,
no duplica filas por ser N:1); `ilike` es portable a SQL Server (`lower() LIKE lower()`).

**Portabilidad SQL Server:** comparaciones `activo == True` (→ `activo = 1`, ADR-014);
tests compilan el filtro de duplicado y el JOIN de búsqueda con el dialecto mssql. Pruebas
de backend en `app/tests/test_f0_02_tarifas.py` (33 casos: neta/redondeo, ausencia de
vigencia, duplicado activo y reactivación, dependencia de Estación, enums —incl.
`producto`—, búsqueda por nombre/siglas/notas, enriquecimiento, y 10 nuevos de auditoría
de `tarifa_bruta`/`descuento_pct` — alta con `anterior=None`, edición con/sin motivo,
permiso no-Admin rechazado, mismo valor no audita, campo no sensible no audita, un solo
motivo audita los dos campos, `motivo_cambio` no es columna, historial completo,
historial 404).

**Historial de auditoría:** `GET /catalogos/tarifas/{id}/historial` (ADR-021, mismo
endpoint que los demás catálogos con campos sensibles) — panel "Historial de cambios" en
el detalle, formato `Tarifa bruta: 9000.00 → 9500 · 21/09/26, 8:00 p.m. · dev.admin ·
Ajuste de temporada` (mismo formato que Agencia/Vendedor/Contrato).

**Ajustes de integración con las pantallas aprobadas (dentro de F0-02):**
- **"Tarifas vigentes" en el panel de Plaza (F0-01) — RETIRADO (ADR-097):** existía porque
  la tarifa vivía por plaza y con vigencia; al desaparecer ambos conceptos, la sección
  completa (y su hook `useTarifasVigentesPorPlaza`) se eliminó del panel de detalle de
  Plaza. Ya no hay un lugar equivalente que muestre "tarifas de esta X" — se puede volver a
  agregar (esta vez del lado de Estación) si el negocio lo pide.
- **Contadores del sidebar del explorador (F0-00):** el menú muestra el conteo real solo de
  los catálogos ya implementados, reutilizando el `total` del listado paginado (una
  consulta `size:1` por catálogo). Los catálogos aún no implementados (F0-03/04/05) siguen
  en 0 sin error.
- **`OrdenEstacionDetailPanel` (F1):** el desvío contra la tarifa de referencia
  (`tarifaReferencia` en `state/catalogosCache.ts`) ahora busca por `estacion_id` en vez de
  `plaza_id` — más directo, ya que el componente ya resuelve la `Estacion` de la
  `OrdenEstacion`.

## Pendientes / dudas
- (Resuelto, histórico) La tarifa era por **plaza + señal + duración** (no por estación).
- (Resuelto E-1..E-5) Ver "Estado de implementación" — varias superadas por ADR-097.
- (Resuelto ADR-097) La tarifa es por **estación** (no por plaza), agrega **producto**, y
  ya NO tiene vigencia.
- (Resuelto ADR-098) `duracion_spot` ya no acepta `mencion` (vive solo en `producto`).
- (Resuelto ADR-099) `tarifa_bruta`/`descuento_pct` son parámetros sensibles con
  auditoría e historial, mismo mecanismo que Agencia/Vendedor/Contrato.
