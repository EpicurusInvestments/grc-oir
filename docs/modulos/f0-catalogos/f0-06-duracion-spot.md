# Módulo F0-06 — Producto Duración (DuracionSpotCatalogo) · Fase: F0

> Catálogo NUEVO, fuera de la spec BD v2, agregado DESPUÉS de que F0 ya se diera por
> completa (ver nota en `f0-00-indice.md`). Referencia: **ADR-159** en
> `docs/arquitectura.md`.
>
> **ADR-159 (petición del usuario, 2026-10-05):** "no quiero que modifiques nada de los
> ENUMS donde configuras el tiempo de los Spots vamos a crear un catálogo nuevo llamado
> DuracionSpots... solo crea el catálogo por ahora no lo usaremos solo quiero ver el
> CRUD completo."
>
> **ADR-164 (petición del usuario, 2026-10-06):** "el campo producto ya no es un
> selector ahora deberá permitir darlo de alta como un input" — `producto` dejó de
> reusar el enum/CHECK `ProductoTarifa` de Tarifa y pasó a texto libre.
>
> **ADR-165 (petición del usuario, 2026-10-06):** "descripción de la duración" pasa a
> ser OPCIONAL — si se deja vacía, se guarda como el literal "sin resultado" (equivale a
> nulo), para productos (p.ej. Mención) donde no siempre se quiere capturar una duración.
>
> **ADR-166 (petición del usuario, 2026-10-06):** Tarifa (F0-02) es la PRIMERA pantalla
> que se conecta a este catálogo — "Producto" y "Duración" ahí ahora se eligen de aquí en
> vez de un selector fijo. Ver ADR-166 en `docs/arquitectura.md` y la ficha `f0-02-tarifas.md`.

## Propósito

Catálogo administrable de duraciones posibles, agrupadas por **producto**
(spot│mención│control_remoto│patrocinio), para poder "ir agregándole más tiempo etc."
sin requerir una migración por cada valor nuevo — a diferencia del enum `DuracionSpot`
(`app/shared/enums.py`, `20s|30s|60s`) que SIGUE siendo la fuente de verdad para
`TarifaPlaza`/`OrdenCliente`/`OrdenEstacion` y que este módulo **no toca ni reemplaza**.

**Desde ADR-166, Tarifa (F0-02) SÍ lo consume** (Producto/Duración del formulario salen
de aquí). Órdenes (F1) sigue sin conectarse, a propósito, por ahora — petición futura.

## Entidad

### DuracionSpotCatalogo (6 campos)
`duracion_spot_catalogo_id` (PK), `producto` (texto libre, NVARCHAR(60) — **sin CHECK**
desde ADR-164), `descripcion_duracion` (texto libre, NVARCHAR(60) — **sin CHECK**, a
propósito desde el inicio: es justo lo que permite agregar valores nuevos sin
migración; **opcional desde ADR-165**), `activo`, `created_at`, `updated_at`.

- **`producto` es TEXTO LIBRE (ADR-164):** originalmente (ADR-159) reusaba el enum/CHECK
  `ProductoTarifa` de `tarifa.py`; el usuario pidió soltar esa restricción también — el
  propósito del catálogo completo es poder "ir agregando más" sin migración, y el enum
  dejaba `producto` tan cerrado como `DuracionSpot`. Migración `d4cf0a32e875` quita el
  CHECK y amplía la columna de `Unicode(20)` a `Unicode(60)`.
- **`descripcion_duracion` es TEXTO LIBRE, no un ENUM cerrado:** decisión deliberada —
  el valor sembrado hoy (20/30/60 para spot; 1/2/3/sin duración para mención; sin
  duración para control remoto y patrocinio) es solo el punto de partida que el usuario
  va a dar de alta manualmente desde la pantalla, no un seed automático.
- **`descripcion_duracion` es OPCIONAL (ADR-165):** si se deja vacía (al crear o editar),
  el servicio la guarda como el literal `SIN_RESULTADO` ("sin resultado", constante
  exportada para que otros módulos la importen en vez de repetir el texto). Equivale a
  "no se capturó ninguna duración real para este producto" — útil para productos como
  Mención donde no siempre aplica. Este literal participa igual en la regla de "sin
  duplicado" de abajo, pero Tarifa (F0-02, ADR-166) lo RECHAZA como duración válida.
- **Sin duplicado (producto + descripcion_duracion, AMBOS case-insensitive):** mismo
  criterio que `Categoria` (ADR-017) pero sobre 2 campos — permite que "sin duración" (o
  "sin resultado") se repita para productos DISTINTOS sin chocar entre sí, y rechaza
  "Spot" si ya existe "spot" para la misma descripción (ADR-164 extendió el
  case-insensitive a `producto`).

## Estados
- Solo `activo` (baja lógica, patrón F0 estándar).

## Pantallas
- Lista + detalle con filtros (Activos/Inactivos/Todos), búsqueda por descripción y
  paginación por página — patrón idéntico a `Categoria` (F0-04).
- Formulario: Producto (input de texto libre desde ADR-164; antes era un `<select>` con
  `PRODUCTO_OPCIONES` de Tarifa), Descripción de la duración (texto libre, OPCIONAL desde
  ADR-165 — con nota explicando el default "sin resultado" si se deja vacía).
- Menú: grupo **"Operación"** (junto a Tarifas), entrada "Producto Duración" (ADR-163:
  renombrado desde "Duración de Spots").

## Roles / permisos
- **Captura: solo Admin (IT)**, igual que el resto de F0. Lectura: demás áreas.

## Reglas de negocio clave
- **Sin duplicado activo (409 `conflicto`):** para la misma combinación producto +
  descripción (case-insensitive), no puede existir otro registro activo.
- **Descripción vacía → "sin resultado" (ADR-165):** ver detalle arriba.
- **Renombrar `producto` propaga en cascada (ADR-172):** al editar el `producto` de UN
  registro (p.ej. corregir el typo "mención" -> "mensión"), TODOS los registros que
  compartían el valor anterior (case-insensitive) se renombran junto con él — si alguno
  de esos renombres chocaría con un registro ya existente para el producto nuevo, se
  rechaza TODO el cambio (409 `conflicto`), sin dejar nada a medias.
- Sin campos calculados ni sensibles — catálogo simple.

## Integraciones
- **Tarifa (F0-02) lo consume desde ADR-166** (Producto/Duración del formulario salen de
  aquí; "sin resultado" ahí está prohibido). Órdenes (F1) sigue sin conectarse, a
  propósito, por ahora.

## Dependencias
- F0-00 (fundamentos) únicamente. Desde ADR-164 ya no depende del enum `ProductoTarifa`
  de `tarifa.py` (F0-02) — `producto` es texto libre propio de este catálogo. (La
  dependencia INVERSA — Tarifa depende de este catálogo desde ADR-166 — se documenta en
  `f0-02-tarifas.md`.)

## Estado de implementación

Implementado sobre la base de F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`),
mismo patrón que `Categoria`. Modelo, schemas, repositorio y servicio en
`backend/app/modules/catalogos/duracion_spot_catalogo.py`; migraciones
`20261005_1330-2047cd2e1d53_f0_06_duracion_spot_catalogo.py` (tabla nueva, sin FKs
entrantes ni salientes) y `20261006_1349-d4cf0a32e875_..._producto_libre.py` (ADR-164:
quita el CHECK de `producto`, amplía la columna). Pantalla en
`frontend/src/modules/catalogos/duracionSpot/`. Endpoints en `docs/API-CONTRACT.md`
(sección Producto Duración).

**Pruebas de backend** en `app/tests/test_f0_06_duracion_spot_catalogo.py` (19 casos:
alta básica, duplicado mismo producto+descripción rechazado, distinto producto misma
descripción NO duplica, edición sin chocar consigo misma, edición a un duplicado
existente rechazada, baja lógica, producto texto libre acepta valor nuevo (ADR-164),
producto vacío rechazado, producto con distinta capitalización SÍ duplica (ADR-164),
descripción vacía/omitida default "sin resultado" (ADR-165, 2 casos), edición limpia a
"sin resultado" (ADR-165), búsqueda por descripción, renombrar producto en cascada a
hermanos / sin afectar otros productos / sin tocar nada si no hay cambio real / rechazo
si choca con un existente (ADR-172, 4 casos), y 2 de portabilidad SQL Server —
`func.lower`/`activo = 1`).

**Verificado en vivo** contra el backend real corriendo: se crearon los 9 registros de
ejemplo (spot: 20/30/60; mención: 1/2/3/sin duración; control remoto: sin duración;
patrocinio: sin duración) vía `POST /catalogos/duraciones-spot`, confirmado el listado
(`total: 9`) y el rechazo 409 de un duplicado exacto.

## Pendientes / dudas
- (Resuelto ADR-159) El catálogo se crea standalone, sin wiring a Tarifa/Órdenes.
- (Resuelto ADR-166) Tarifa (F0-02) ya se conecta — `TarifaForm.tsx` elige Producto y
  Duración de aquí.
- **Pendiente, petición futura:** conectar también Órdenes (reemplazar los `<select>` de
  `OrdenClienteForm.tsx`/`OrdenEstacionForm.tsx` por este catálogo). No se asume ninguna
  fecha ni alcance para ese paso. Mientras tanto, cualquier producto/duración NUEVO
  capturado solo en Tarifa no será "sugerido" en Órdenes (`_tarifa_sugerida`,
  `orden_estacion.py`) hasta que esa pantalla también se conecte.
