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

## Pendientes / dudas
- (Resuelto) La tarifa es por **plaza + señal + duración** (no por estación).
