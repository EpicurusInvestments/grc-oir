# Módulo F4 — Reportes y Consulta · Fase: F4

> **Estado: IMPLEMENTADA (3 tandas completas, 2026-11-26).**
> Módulo de código único `reportes` (mismo criterio que F2/F3), entregado en 3 tandas.
> **Solo lectura:** F4 no captura nada ni escribe datos de negocio; consulta y agrega lo que
> ya existe en F1–F3. Referencias: spec BD v2 (`PeriodoResultados`), mockup
> `Fase_4_-_Reportes.html` (4 vistas), `arquitectura.md` (ADR-025 exportación/CSV-injection,
> ADR-039 aritmética de dinero, ADR-040 Admin superusuario, ADR-044 claves RBAC por módulo,
> ADR-064 N:M orden↔factura, ADR-271/286 cancelación de pagos, ADR-290 subtotal/IVA manual
> en facturas recibidas), fichas F2/F3, `glosario.md`.
> Refinada en sesión de planeación del 2026-11-26.

## Propósito

Dar a Dirección y a las áreas operativas una vista consolidada del negocio: Estado de
resultados (P&L) mensual y tres dashboards (Comercial, Cobranza, Operativo), todos
exportables a Excel/CSV. Es la Entrega 4 (junto con F5).

## Decisiones confirmadas (sesión 2026-11-26)

| # | Tema | Decisión |
|---|---|---|
| 1 | IVA | El **P&L es SIN IVA**. |
| 2 | Fecha de cobro | El cobrado se asigna al mes por **`fecha_pago_cliente`** (no `fecha_deposito`). |
| 3 | Costos de proveedor | Cada costo (Afiliados, Agencias, Vendedores) se divide en **2 subrenglones**: *Facturado en el periodo* y *Pagado en el periodo*, igual que Ingresos. |
| 4 | Qué requisiciones cuentan | Solo `pagada` cuenta como *Pagado en el periodo*; lo demás vive en *Facturado en el periodo*. |
| 5 | Cierre de período | **NO hay cierre ni snapshots.** Todo se calcula en vivo. **`PeriodoResultados` NO se persiste** (desviación consciente de la spec; ADR a escribir). |
| 6 | "Ventas" (dashboard comercial) | `OrdenCliente.total` de órdenes **no canceladas**. |
| 7 | Aging | Cubetas del glosario: **corriente, 1-30, 31-60, 61-90, 90+**, por **días vencidos** (contra `fecha_estimada_cobro`). |
| 8 | DSO | Fórmula **clásica**: saldo por cobrar / ventas facturadas × días de la ventana. |
| 9 | Dashboard operativo | Ordenado vs. ejecutado **sin spots bonificables** (entran en una versión posterior) — **implementado como "no se restan por ahora"** (Tanda 3): `cantidad_spots_bonificables` no se descuenta de `spots_asignados`/`spots_verificados` porque el modelo no separa esos spots a nivel de día; solo cuentan días con `Verificacion` ya creada y `cancelada=False`. Tasa de incidencias = incidencias / OE totales del afiliado (mismo conjunto "día verificado"). "Afiliados activos" = con actividad (día verificado) en la ventana. |
| 10 | Volumen | ~80 órdenes/facturas por mes → **agregar en SQL** (GROUP BY), nunca fila por fila ni N+1. |
| 11 | Validación | No hay P&L real de referencia: se valida contra consultas SQL independientes en SSMS. |

## Vistas

### 1. Estado de resultados (`reportes_financiero`)

Selector de **mes** (`YYYY-MM`); el mes en curso se rotula "(en curso)". Compara contra el
mes anterior (tendencia %) y muestra histórico de 6 meses. Moneda MXN. **Todo sin IVA.**

```
INGRESOS
  Facturado en el periodo      SUM(FacturaCliente.subtotal_factura)   por fecha de factura, sin canceladas
  Cobrado en el periodo        SUM(PagoCliente.monto_aplicado) sin IVA, por fecha_pago_cliente,
                               excluye estatus_pago = 'cancelado', no incluye `ajuste`
COSTOS DIRECTOS
  Pagos a afiliados            Facturado en el periodo (FacturaAfiliado, sin canceladas)
                               Pagado en el periodo (Requisicion pago_afiliado, estatus pagada)
  Pagos a agencias             Facturado (FacturaAgencia) / Pagado (Requisicion pago_agencia pagada)
  Comisiones a vendedores      Facturado (FacturaVendedor) / Pagado (Requisicion comision_vendedor pagada)
  Comisiones a agencias (req.) Requisicion comision_agencia pagada (solo se muestra si > 0)
COSTOS INDIRECTOS
  Nóminas                      SUM(CostoAdicional.monto_costo) tipo_costo='nomina', periodo_contable = periodo
  Overhead                     SUM(CostoAdicional.monto_costo) tipo_costo='overhead', periodo_contable = periodo
```

- **Utilidad bruta** = Cobrado − (Pagado afiliados + Pagado agencias + Pagado comisiones
  vendedores + Pagado comisiones agencias). Base **caja**, como la fórmula de la spec. Los
  subrenglones *Facturado* de costos son informativos (no entran a la fórmula).
- **Utilidad neta** = Utilidad bruta − Nóminas − Overhead.
- Indicadores: margen bruto %, margen neto %, % cobranza (cobrado/facturado), costo
  afiliados/cobrado.
- **Corrección de la spec:** la spec dice `SUM(requisicion_comision_vendedor)`. Desde
  ADR-219 las requisiciones de ese tipo ya no traen `orden_id`, así que esa columna queda
  vacía. La fuente real es `Requisicion.monto_requisicion` por `tipo_requisicion`.
- **Sin IVA con pagos:** el pago entra con IVA. Para llevarlo a sin IVA se prorratea por
  factura (`monto_aplicado × subtotal_factura / total_factura`, `ROUND(x,2)`). Lo mismo
  aplica a costos pagados: `monto_requisicion` **sí incluye IVA** (confirmado con el
  equipo), se prorratea igual contra la factura de proveedor ligada. Regla de redondeo
  y arquitectura: ADR-039.
- Reglas de exclusión: facturas `cancelada` fuera; pagos `cancelado` fuera. Pagos
  huérfanos (`cobranza_id IS NULL`) **no** entran al cobrado (no hay factura de la que
  derivar el IVA). Los checkboxes "externo" (ADR-248/256) **sí** entran (solo identifican).

### 2. Dashboard comercial (`reportes_comercial`)

Selector: YTD, mes, trimestre. KPIs: ventas, ticket promedio (ventas / # órdenes),
comisiones de vendedores, anunciantes con ventas. Cortes (Top N): vendedor, anunciante,
**Giro Empresarial** (`Categoria`), agencia (incluye "Trato directo" = sin agencia), más
evolución mensual.
- Ventas = `OrdenCliente.total` con `estatus_orden <> 'cancelada'`.
- Vendedor = vendedor **principal** de la orden; comisión = `total × porcentaje_snap / 100`
  (los `%_snap` ya congelados en la orden). Supuesto a confirmar: el secundario no suma
  ventas pero su comisión se reporta aparte.
- Fecha de la venta: la define el plan (propuesta: fecha de captura/recepción de la orden).

### 3. Dashboard de cobranza (`reportes_cobranza`)

"Al corte" (hoy). KPIs: total por cobrar, vencido, DSO, cobrado del mes.
- **Saldo por cobrar** = total de la factura − pagos no cancelados, de `CobranzaFactura`
  con `estatus_cobro <> 'cobrada'`. Aquí el saldo es **con IVA** (es dinero a recibir);
  el P&L es el único reporte sin IVA — rotularlo.
- **Aging** (por días vencidos = hoy − `fecha_estimada_cobro`): corriente (no vencida),
  1-30, 31-60, 61-90, 90+. Importe y # de facturas por cubeta.
- **DSO** = saldo por cobrar / ventas facturadas en la ventana × días de la ventana
  (ventana por omisión: últimos 90 días; el plan la fija y la expone). Global y por cliente.
- Tabla por anunciante: por cobrar, vencido, DSO. Gráfica cobrado vs. facturado por mes.
- Todo con GROUP BY en SQL; no reutilizar el cálculo fila por fila de ADR-277 (aquel es
  por un solo anunciante).

### 4. Dashboard operativo (`reportes_operativo`)

Selector: YTD, mes. KPIs: cumplimiento general, spots transmitidos, incidencias, afiliados
activos.
- **Cumplimiento por estación:** spots ordenados (`OrdenEstacion`) vs. ejecutados
  (verificación), % = ejecutado/ordenado. **Sin bonificables.**
- **Incidencias por afiliado:** total y por tipo (faltante, excedente, cambio_horario,
  cambio_fecha, spot_no_emitido); **tasa = incidencias / OE totales del afiliado**; >10%
  resalta. Afiliado se llega vía Estación → Afiliado.
- Composición de incidencias por tipo.

## Exportación a Excel/CSV (transversal)

- Las 4 vistas exportan sus tablas. Utilidad reutilizable en `app/shared/` (no en el
  módulo), formatos `.xlsx` y `.csv`.
- **Neutralizar CSV/formula injection** (`= + - @` al inicio de celda de texto) — pendiente
  desde ADR-025.
- Los endpoints de exportación llevan el MISMO RBAC que su vista.
- **Auditar exportaciones** (quién, cuándo, qué reporte, filtros) al log de la aplicación.
- Montos numéricos reales en Excel (no texto) con 2 decimales.

## Backend

- Módulo `backend/app/modules/reportes/` (router → service → repository). Los repositorios
  solo hacen consultas agregadas (SQL), el service arma KPIs, tendencias y márgenes.
- **Sin migración esperada** (no hay tabla nueva: `PeriodoResultados` no se persiste). Si el
  plan propone índices por rendimiento, es migración y se revisa **antes** de aplicar.
- Endpoints propuestos (los define el plan, `/api/v1/reportes`):
  `GET /estado-resultados`, `GET /comercial`, `GET /cobranza`, `GET /operativo`, y
  `GET /<vista>/exportar?formato=xlsx|csv`.
- Compatibilidad SQL Server: BIT con `== True`, NUMERIC para dinero, sin T-SQL-only en
  `LIKE`, ADR-036 para fechas/horas; la aritmética de dinero se corrobora contra SQL Server
  real (ADR-039), no solo SQLite.
- Solo lectura: ningún endpoint de escritura, ningún `commit`.

## RBAC (todo lectura; Admin es superusuario, ADR-040 — no listarlo)

| Clave | Vista | Quién lee (además de Admin) |
|---|---|---|
| `reportes_financiero` | Estado de resultados | Dirección |
| `reportes_comercial` | Dashboard comercial | Dirección, Ventas |
| `reportes_cobranza` | Dashboard de cobranza | Dirección, Facturación, Tesorería, CxC, CxP |
| `reportes_operativo` | Dashboard operativo | Todas las áreas |

(Patrón de ADR-044: claves separadas por dominio.) La UI oculta las vistas sin permiso; el
backend valida siempre.

## Frontend (`frontend/src/modules/reportes/`)

- Mismo patrón que F2/F3 (types → api → hooks → components → pages → registry).
- Montado en `/reportes`, color de fase **gris** (F4), sidebar al estilo del mockup:
  "Reportes financieros" → Estado de resultados; "Dashboards" → Comercial, Cobranza,
  Operativo (solo se listan los permitidos).
- Activar F4 en `phaseRegistry.ts` (`enabled: true`, `route: "/reportes"`) y actualizar
  `dashboard-navegacion.md` (hoy dice F4 "Próximamente").
- Gráficas simples (barras horizontales/verticales del mockup); sin librería de charts
  salvo que el plan la justifique.
- Botón "Exportar" por vista. Selectores de período del mockup.
- Pruebas de componente: qué vistas/botones ve cada área.

## Fuera de alcance de F4

- Cierre de período / snapshots / reapertura (decisión 5).
- Spots bonificables en cumplimiento (decisión 9).
- Reportes por plaza, alertas, programación de envíos, PDF.
- Cualquier escritura de negocio.

## Tandas

1. **Tanda 1 (IMPLEMENTADA, 2026-11-26):** utilidad de exportación (`app/shared/exportacion.py`)
   + Estado de resultados (back + front) + activar F4 en `phaseRegistry`. Plan completo
   y detalle de esta tanda: `docs/modulos/f4-reportes/f4-Reportes-Plan-completo.md`.
   Módulo backend `app/modules/reportes/` (router → service → repository → schemas);
   frontend `frontend/src/modules/reportes/`. RBAC: se agregaron las 4 claves de una vez
   en `app/core/security.py` (`reportes_financiero`/`_comercial`/`_cobranza`/
   `_operativo`), aunque solo la primera tenga endpoint todavía. Novedad de plomería:
   `PhaseEntry.visibleParaArea` (nuevo campo opcional en `phaseRegistry.ts`) oculta la
   tarjeta/entrada de menú de una fase para áreas sin ningún permiso adentro — F4 es la
   primera fase que lo usa. Sin migración (confirmado: no hay tabla nueva).
2. **Tanda 2 (IMPLEMENTADA, 2026-11-26):** Dashboard comercial (`GET /reportes/comercial`,
   ventanas ytd/mes/trimestre; corte de vendedor secundario corregido — ver "Pendientes/
   dudas" abajo) y Dashboard de cobranza (`GET /reportes/cobranza`, aging agregado en
   UNA consulta, DSO global y por anunciante, "Cobrado del mes" con IVA que SÍ incluye
   huérfanos a diferencia del P&L). 2 nuevas páginas en `reportesRegistry` con sus
   propias áreas (`reportes_comercial`: Dirección/Ventas; `reportes_cobranza`:
   Dirección/Facturación/Tesorería/CxC/CxP). Sin migración. Detalle completo de reglas
   y fórmulas en `API-CONTRACT.md`.
3. **Tanda 3 (IMPLEMENTADA, 2026-11-26):** Dashboard operativo (`GET /reportes/operativo`,
   ventanas ytd/mes/trimestre). Cumplimiento por estación: `OrdenEstacionDia` JOIN
   `Verificacion` (solo días ya verificados, `cancelada=False`) agregado por `Estacion`;
   `cantidad_spots_bonificables` NO se resta (ver decisión 9). Incidencias por afiliado:
   desglose de los 5 tipos (`faltante`/`excedente`/`cambio_horario`/`cambio_fecha`/
   `spot_no_emitido`) vía `Estacion → Afiliado`, con tasa = incidencias / OE totales del
   afiliado (mismo conjunto "día verificado" que cumplimiento) y alerta si > 10%.
   Composición de incidencias: los 5 tipos agregados globalmente. Nueva página
   `reportesRegistry` (`dashboard_operativo`, TODAS las áreas — es la única vista de F4
   que ve Nóminas). Sin migración. Con esta tanda, F4 queda completa.

Cada tanda: plan breve → aprobación → código → validación manual (Swagger/SSMS/navegador)
→ commits por capa → docs. Un PR por módulo, revisión de TI.

## Validación (sin P&L de referencia)

Para cada cifra, Claude Code entrega una consulta SQL **independiente** (escrita distinto al
código de la app) que el desarrollador corre en SSMS contra `DEMO-GRC-OIR` y compara con
Swagger. Casos obligatorios: factura cancelada excluida, pago cancelado excluido, pago huérfano
excluido, factura con varias órdenes (N:M), mes sin datos, mes con utilidad negativa, factura
con subtotal/IVA manual (ADR-290).

## Pendientes / dudas

- **(Confirmado con el equipo, 2026-11-26)** `Requisicion.monto_requisicion` SÍ incluye
  IVA. El *Pagado* de costos directos (afiliados/agencias/comisiones) se prorratea a
  sin-IVA con la razón `monto_factura_* / total_factura_*` de la factura de proveedor
  ligada (o `OrdenCliente.subtotal/total` para `comision_agencia`, que no tiene factura)
  — tal como ya lo implementó Tanda 1.
- (Resuelto, Tanda 1) Nombres reales de fecha: `FacturaCliente.fecha_factura` (también
  usado como `fecha_emision` hacia el PAC — es la fecha de emisión real, no un
  borrador); `FacturaAfiliado/Agencia/Vendedor.fecha_factura_{afiliado|agencia|vendedor}`;
  `Requisicion.fecha_pago_requisicion`; `OrdenCliente.fecha_venta`.
- (Resuelto, Tanda 1) "Facturado en el periodo" en costos = devengado (fecha de factura
  recibida en el mes), mismo criterio que ingresos — confirmado.
- (Resuelto e IMPLEMENTADO, Tanda 2) Vendedor secundario: NO es una identidad fija —
  es un rol POR ORDEN. "Top vendedores" suma la comisión de cada `Vendedor` en ambos
  roles (principal en unas órdenes, secundario en otras, UNA sola fila por vendedor);
  "Ventas" se atribuye una sola vez por orden (al principal), nunca se duplica.
- (Resuelto) Dependencia `.xlsx`: **openpyxl**.
- **(Nuevo, Tanda 1 — hallazgo del pull de `origin/main`)** ADR-293 (Notas de Crédito,
  PR #75) afecta `FacturaCliente`/`PagoCliente`: una NC se neta sola en "Facturado"
  (`subtotal_factura` negativo) y su pago sintético (`factura_egreso_id`) se EXCLUYE de
  "Cobrado" (no es efectivo real). Ver `f4-Reportes-Plan-completo.md`.
- (Resuelto e IMPLEMENTADO, Tanda 3) Dashboard operativo: `Verificacion.reconciliada`
  es hoy un campo MUERTO (siempre `True`, ver `verificacion.py`) — no sirve como filtro
  de "día ya medido"; se usa en su lugar la sola EXISTENCIA de la fila `Verificacion`
  (INNER JOIN) + `OrdenEstacionDia.cancelada = False`. Bonificables: no se restan por
  ahora (ver decisión 9 actualizada arriba) — queda abierto para una versión futura
  separar el conteo de bonificables a nivel de día si el negocio lo pide.
- (Futuro) Cierre de período, bonificables separados por día, PDF.
