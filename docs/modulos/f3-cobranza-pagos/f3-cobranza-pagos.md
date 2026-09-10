# Módulo F3 — Cobranza y Pagos · Fase: F3

> **Estado: REFINADA — lista para generar el plan con Claude Code.**
> Ficha de alcance de TODO el módulo (las 4 entidades se implementan juntas — mismo
> criterio que F1 y F2, que terminaron consolidados por su acoplamiento y por compartir
> infraestructura). Dos dominios dentro del mismo módulo de código: **cobranza** (CxC:
> `CobranzaFactura`+`PagoCliente`) y **pagos** (CxP: `Requisicion`+`MovimientoBancario`),
> con dos claves RBAC separadas — mismo patrón que F2 (ADR-044).
> Referencias: spec BD v2, `CLAUDE.md` (mapa de módulos, integraciones), `arquitectura.md`
> (ADR-002 no-timbrado, ADR-019 estados independientes, ADR-039 aritmética de dinero,
> ADR-040 RBAC, ADR-044/046 patrón de 2 claves + canal de autorización, ADR-047/064
> handoff y cancelación con F2, ADR-048 formato real de PAC ya resuelto — no aplica aquí
> pero es la referencia de cómo resolvimos un hueco de integración similar).
> Refinada en sesión de planeación del [[fecha]], tras confirmar F0+F1+F2+F5-00 en `main`.

## Propósito

Cerrar el ciclo financiero: cobrar las facturas que F2 timbró (`CobranzaFactura` +
`PagoCliente`, CxC) y pagar a afiliados/agencias/vendedores mediante requisiciones
autorizadas (`Requisicion` + `MovimientoBancario` para conciliación bancaria, CxP).
Alimenta el Estado de Resultados de F4.

## El handoff con F2 — nueva regla de sincronización (se define aquí)

Igual que F1→F2 tuvo su handoff (`marcar_facturada`/`revertir_facturacion`), F2→F3 tiene
el suyo, con la misma disciplina de "método acotado en el dueño del agregado, invocado en
la misma transacción":

- **Al crear**: cuando `FacturaCliente.estado_facturacion` llega a `timbrada`, se crea
  automáticamente su `CobranzaFactura` (1:1, confirmado en la spec — no cambió con
  ADR-064). Mecanismo: `FacturaClienteService`, en el mismo punto donde ya invoca
  `OrdenClienteService.marcar_facturada()`, invoca también
  `CobranzaService.crear_para_factura(factura)` — misma transacción, sin commit propio.
- **Al cancelar**: si se cancela una `FacturaCliente` que ya tiene `CobranzaFactura` con
  `importe_cobrado > 0` (ya se recibió algún pago), la cancelación se **rechaza** con
  `400 error_dominio` — mismo criterio que la excepción de "OC ya cobrada" de ADR-047: no
  se puede deshacer una factura con dinero real ya recibido. Si `importe_cobrado = 0`
  (nadie ha pagado nada), la `CobranzaFactura` se elimina junto con la reversión.
  **Esta regla es una decisión mía, extendiendo el patrón ya aprobado — avísame si no es
  la que quieres antes de que se implemente.**

## Entidades (spec BD v2, con las 3 desviaciones aditivas de esta sesión)

### CobranzaFactura (14 campos spec, con 2 ajustes)
PK `cobranza_id`. FK `FacturaCliente` (1:1), `anunciante_id` (derivado de la factura),
`metodo_pago_id` — **incoherencia de spec, mismo caso que `FacturaCliente.metodo_pago_clave`
en F2**: no existe tabla `MetodoPago` propia (vive en `ConstantesSistema`), así que este
campo se implementa igual, como `metodo_pago_clave` (texto, sin FK formal).
`dias_credito` (sugerido de `Anunciante.dias_credito_default`, editable).
`fecha_estimada_cobro = FacturaCliente.fecha_entrega_factura + dias_credito` (calculado).

**Ajuste 1 — `importe_cobrado` e `importe_pendiente_cobro`: derivados en lectura, NO
columnas persistidas.** La spec los marca "Calculado" pero son una suma viva
(`SUM(PagoCliente.monto_aplicado)`) que puede cambiar en cualquier momento — persistirlos
arriesgaría que queden desincronizados si algo falla a medio camino. Se calculan en cada
`GET`/al recalcular, nunca se escriben en la tabla.

**Ajuste 2 — `estatus_cobro`: el CHECK solo admite 3 valores almacenados**
(`pendiente`/`cobro_parcial`/`cobrada`); **`vencida` es un badge derivado**, calculado en
el servicio comparando `fecha_estimada_cobro` contra hoy (mismo patrón que
`Vigente`/`Expirada` de `TarifaPlaza` en F0-02) — nunca se escribe en la columna.
`estatus_cobro` (el valor almacenado) se recalcula automáticamente **cada vez que se
inserta o borra un `PagoCliente`** — no es una transición manual con endpoint dedicado
como las máquinas de estado de F1/F2; es un valor derivado de la suma de pagos, igual
que `spots_faltantes` en F1-02.

**Ajuste 3 — `fecha_cobro` se asigna automáticamente**, no se captura manual (aunque la
spec la marca "Manual"): el servicio la fija en el momento en que `estatus_cobro` pasa a
`cobrada` (cuando `importe_cobrado >= total_factura`). Deviación menor, documentar.

### PagoCliente (10 campos spec, sin ajustes)
PK `pago_cliente_id`. FK `CobranzaFactura` (N:1). Captura manual por **CxC**.
`metodo_pago_clave` (mismo ajuste que arriba — texto, no FK). Al crear/borrar un
`PagoCliente`, el servicio recalcula `CobranzaFactura.estatus_cobro` y `fecha_cobro`.

### Requisicion (23 campos spec, sin ajustes estructurales)
PK `requisicion_id`. `tipo_requisicion` ENUM (`pago_afiliado`/`pago_agencia`/
`comision_vendedor`/`comision_agencia`). FKs opcionales según el tipo (`factura_afiliado_id`,
`factura_agencia_id`, `orden_id`, `afiliado_id`, `agencia_id`, `vendedor_comision_id`).
Captura por **CxP**. Calculados: `requisicion_comision_vendedor = OrdenCliente.total *
porcentaje_comision_vendedor / 100`; `requisicion_comision_agencia` análogo;
`diferencia_afiliada = monto_requisicion - FacturaAfiliado.total_factura_afiliado`
(monitoreo de márgenes, puede ser negativa — no llevar `CHECK >= 0` en ese campo).

**Máquina de estados real** (con endpoint dedicado, mismo mecanismo de seams que F1/F2):
`pendiente → autorizada → pagada`, rama a `cancelada` desde `pendiente`/`autorizada`.
**Autorización**: el paso `pendiente→autorizada` requiere **Dirección o Admin** (mismo
canal dedicado del ADR-046 — permiso de router en `pagos:leer`, chequeo de área real
dentro del servicio) — CxP captura pero no se autoriza a sí mismo. Extensión directa del
patrón ya aprobado en F2.

### MovimientoBancario (11 campos spec, sin ajustes)
PK `movimiento_id`. `tipo_movimiento` ENUM (`cargo`/`abono`). Captura por **Tesorería**
(nueva área que escribe en este módulo — hasta ahora Tesorería solo leía). `conciliado`
BOOLEAN, cambiado **solo manualmente** vía botón "Conciliar" (confirmado: sin matching
automático en esta versión — el mockup mismo lo deja como "sin coincidencias
automáticas"). Sin máquina de estados.

## RBAC (confirmado)

| Entidad | Quién captura | Quién solo lee |
|---|---|---|
| `CobranzaFactura`, `PagoCliente` | CxC | Ventas, Facturación, Tesorería, CxP, Dirección, Nóminas |
| `Requisicion`, `MovimientoBancario` | CxP (Requisicion) / **Tesorería** (MovimientoBancario) | el resto |

Admin superusuario automático (ADR-040) — no listarlo. La autorización de `Requisicion`
(Dirección/Admin) es un chequeo de servicio, no de RBAC de módulo — igual que
`FacturaAfiliado`/`FacturaAgencia` en F2.

## Convenciones técnicas obligatorias (heredadas de F1/F2)

- `app/shared/` para infra CRUD genérica.
- `fecha_sql()`/`hora_sql()`/`texto_largo()` de `core/db.py` para columnas de fecha/hora/
  texto largo.
- `ROUND(x,2)` en cualquier `CHECK` de igualdad de dinero (ADR-039) — aquí no hay tantos
  como en F2 porque los importes de cobranza son derivados, no columnas con CHECK, pero
  si `Requisicion` termina con algún CHECK de suma, aplica igual.
- PKs UUID, snake_case español, `created_at`/`updated_at`/`created_by`.
- Adjuntos: mismo patrón genérico (router hermano, no tocar F1/F2) para comprobantes de
  pago, archivo del movimiento bancario, XML/PDF de facturas de proveedor si se cargan.

## Integraciones — 2 huecos conocidos, mismo tratamiento que el PAC en F2

- **Formato de estados de cuenta bancarios**: `[[POR LLENAR: banco(s) y formato]]`. La
  carga manual (captura uno por uno, como en el mockup) **no depende de esto** y se
  construye ya; la carga por archivo se aísla en un puerto+adaptador placeholder
  (`ExtractoBancarioPort`), igual que `TimbradoExportPort` en F2 — sin bloquear el resto.
- **Formato del NOI de nóminas**: `[[POR LLENAR]]` — es técnicamente de `CostoAdicional`
  (F2), no de F3, pero se menciona aquí porque comparte el mismo tratamiento de puerto
  aislado si se retoma.
- **SAP**: solo referencia (`numero_oc_sap` como texto), sin integración real — ya así en
  la spec, sin cambios.

## Reglas generales de integración (de `CLAUDE.md`, aplican aquí)

- Nunca parsear un formato externo desde un router o componente — siempre en la capa de
  integración (`app/integrations/`).
- Cargas de archivo grandes no deben bloquear el request; si el volumen lo justifica,
  usar `BackgroundTasks` (a evaluar en el plan técnico, no es una decisión de negocio).
- Auditar cargas y exportaciones (quién, cuándo, qué archivo, resultado).
- Validar duplicados en `MovimientoBancario` (mismo banco+fecha+referencia+monto) antes
  de insertar.

## Roles / permisos — nota sobre Tesorería

Este es el primer módulo donde **Tesorería pasa de "solo lectura" a "captura"**
(`MovimientoBancario`). Confirmar que la matriz RBAC ya contempla esto sin fricción (debería,
ya que el área existe desde F0, solo no había tenido permiso de escritura hasta ahora).

## Dependencias

- F2 completo (`FacturaCliente` timbrada, `FacturaAfiliado`/`FacturaAgencia` autorizadas).
- F0 completo (`Anunciante.dias_credito_default`, `ConstantesSistema` para métodos de
  pago, `Afiliado`/`Agencia`/`Vendedor`). F5-00 (RBAC real).

## Pendientes (no bloquean el arranque de F3)

- Formato real de estados de cuenta bancarios (puerto aislado, placeholder mientras).
- Si el negocio pide matching automático de conciliación más adelante, es una extensión
  sobre `MovimientoBancario`, no un rediseño.
