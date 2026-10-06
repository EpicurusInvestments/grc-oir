# Módulo F0-06 — Duración de Spots (DuracionSpotCatalogo) · Fase: F0

> Catálogo NUEVO, fuera de la spec BD v2, agregado DESPUÉS de que F0 ya se diera por
> completa (ver nota en `f0-00-indice.md`). Referencia: **ADR-159** en
> `docs/arquitectura.md`.
>
> **ADR-159 (petición del usuario, 2026-10-05):** "no quiero que modifiques nada de los
> ENUMS donde configuras el tiempo de los Spots vamos a crear un catálogo nuevo llamado
> DuracionSpots... solo crea el catálogo por ahora no lo usaremos solo quiero ver el
> CRUD completo."

## Propósito

Catálogo administrable de duraciones posibles, agrupadas por **producto**
(spot│mención│control_remoto│patrocinio), para poder "ir agregándole más tiempo etc."
sin requerir una migración por cada valor nuevo — a diferencia del enum `DuracionSpot`
(`app/shared/enums.py`, `20s|30s|60s`) que SIGUE siendo la fuente de verdad para
`TarifaPlaza`/`OrdenCliente`/`OrdenEstacion` y que este módulo **no toca ni reemplaza**.

**Por ahora NINGUNA otra pantalla ni módulo usa este catálogo** — es solo el CRUD,
desconectado del resto del sistema, a petición expresa del usuario.

## Entidad

### DuracionSpotCatalogo (6 campos)
`duracion_spot_catalogo_id` (PK), `producto` (ENUM reusado de `ProductoTarifa`,
`tarifa.py` — fm│am│tv NO aplica aquí, es spot│mencion│control_remoto│patrocinio, CHECK
`ck_duracion_spot_catalogo_producto`), `descripcion_duracion` (texto libre, NVARCHAR(60)
— **sin CHECK**, a propósito: es justo lo que permite agregar valores nuevos sin
migración), `activo`, `created_at`, `updated_at`.

- **`producto` reusa `ProductoTarifa`** (no se duplica el enum): mismo criterio de "no
  repetir una fuente de verdad" ya establecido para `DuracionSpot` (ADR-032).
- **`descripcion_duracion` es TEXTO LIBRE, no un ENUM cerrado:** decisión deliberada —
  el valor sembrado hoy (20/30/60 para spot; 1/2/3/sin duración para mención; sin
  duración para control remoto y patrocinio) es solo el punto de partida que el usuario
  va a dar de alta manualmente desde la pantalla, no un seed automático.
- **Sin duplicado (producto + descripcion_duracion, case-insensitive):** mismo criterio
  que `Categoria` (ADR-017) pero sobre 2 campos — permite que "sin duración" se repita
  para productos DISTINTOS (control_remoto y patrocinio) sin chocar entre sí.

## Estados
- Solo `activo` (baja lógica, patrón F0 estándar).

## Pantallas
- Lista + detalle con filtros (Activos/Inactivos/Todos), búsqueda por descripción y
  paginación por página — patrón idéntico a `Categoria` (F0-04).
- Formulario: Producto (select, reusa `PRODUCTO_OPCIONES` de Tarifa), Descripción de la
  duración (texto libre).
- Menú: grupo **"Operación"** (junto a Tarifas), entrada "Duración de Spots".

## Roles / permisos
- **Captura: solo Admin (IT)**, igual que el resto de F0. Lectura: demás áreas.

## Reglas de negocio clave
- **Sin duplicado activo (409 `conflicto`):** para la misma combinación producto +
  descripción (case-insensitive), no puede existir otro registro activo.
- Sin campos calculados ni sensibles — catálogo simple.

## Integraciones
- Ninguna. No lo consume Tarifa ni Órdenes (a propósito, por ahora).

## Dependencias
- F0-00 (fundamentos) y el enum `ProductoTarifa` ya existente en `tarifa.py` (F0-02) —
  mismo criterio de reuso que cualquier otro catálogo que referencia un enum compartido.

## Estado de implementación

Implementado sobre la base de F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`),
mismo patrón que `Categoria`. Modelo, schemas, repositorio y servicio en
`backend/app/modules/catalogos/duracion_spot_catalogo.py`; migración
`20261005_1330-2047cd2e1d53_f0_06_duracion_spot_catalogo.py` (tabla nueva, sin FKs
entrantes ni salientes). Pantalla en
`frontend/src/modules/catalogos/duracionSpot/`. Endpoints en `docs/API-CONTRACT.md`
(sección Duración de Spots).

**Pruebas de backend** en `app/tests/test_f0_06_duracion_spot_catalogo.py` (11 casos:
alta básica, duplicado mismo producto+descripción rechazado, distinto producto misma
descripción NO duplica, edición sin chocar consigo misma, edición a un duplicado
existente rechazada, baja lógica, producto inválido rechazado, descripción vacía
rechazada, búsqueda por descripción, y 2 de portabilidad SQL Server —
`func.lower`/`activo = 1`).

**Verificado en vivo** contra el backend real corriendo: se crearon los 9 registros de
ejemplo (spot: 20/30/60; mención: 1/2/3/sin duración; control remoto: sin duración;
patrocinio: sin duración) vía `POST /catalogos/duraciones-spot`, confirmado el listado
(`total: 9`) y el rechazo 409 de un duplicado exacto.

## Pendientes / dudas
- (Resuelto ADR-159) El catálogo se crea standalone, sin wiring a Tarifa/Órdenes — queda
  pendiente, para una petición futura del usuario, decidir SI y CÓMO se conecta (p. ej.
  reemplazar el `<select>` de duración de `TarifaForm.tsx`/`OrdenClienteForm.tsx`/
  `OrdenEstacionForm.tsx` por este catálogo). No se asume ninguna fecha ni alcance para
  ese paso siguiente.
