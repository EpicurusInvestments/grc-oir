# Módulo F3 — Cobranza y Pagos · Fase: F3

> **Estado: IMPLEMENTADA (backend + frontend) — 2026-09-09.**
> Ficha de alcance de TODO el módulo (las 4 entidades se implementan juntas — mismo
> criterio que F1 y F2, que terminaron consolidados por su acoplamiento y por compartir
> infraestructura). Dos dominios dentro del mismo módulo de código: **cobranza** (CxC:
> `CobranzaFactura`+`PagoCliente`) y **pagos** (CxP: `Requisicion`+`MovimientoBancario`),
> con dos claves RBAC separadas — mismo patrón que F2 (ADR-044).
> Referencias: spec BD v2, `CLAUDE.md` (mapa de módulos, integraciones), `arquitectura.md`
> (ADR-002 no-timbrado, ADR-019 estados independientes, ADR-039 aritmética de dinero,
> ADR-040 RBAC, ADR-044/046 patrón de 2 claves + canal de autorización, ADR-047/064
> handoff y cancelación con F2, ADR-048 formato real de PAC ya resuelto — no aplica aquí
> pero es la referencia de cómo resolvimos un hueco de integración similar, ADR-071
> factory compartida de adjuntos — F3 fue el tercer consumidor que la justificó,
> **ADR-072 el handoff F2↔F3 completo tal como quedó implementado, ADR-073 el canal
> dedicado de Tesorería, ADR-074 el deep-link F2→F3 y el patrón "amplía y filtra en el
> cliente" del frontend**).
> Refinada en sesión de planeación del 2026-09-09, tras confirmar F0+F1+F2+F5-00 en `main`.
> Implementada la misma sesión — backend completo (modelos, migración, servicios,
> routers, RBAC, 28 pruebas) y frontend completo (8 páginas, 4 formularios, registry +
> explorador, deep-link F2→F3, 21 pruebas de componente) — ver sección "Frontend" abajo.

## Propósito

Cerrar el ciclo financiero: cobrar las facturas que F2 timbró (`CobranzaFactura` +
`PagoCliente`, CxC) y pagar a afiliados/agencias/vendedores mediante requisiciones
autorizadas (`Requisicion` + `MovimientoBancario` para conciliación bancaria, CxP).
Alimenta el Estado de Resultados de F4.

## El handoff con F2 — cómo quedó implementado (ADR-072)

Igual que F1→F2 tuvo su handoff (`marcar_facturada`/`revertir_facturacion`), F2→F3 tiene
el suyo, con la misma disciplina de "método acotado en el dueño del agregado, invocado en
la misma transacción, sin `commit` propio":

- **Al crear**: cuando `FacturaCliente.estado_facturacion` llega a `timbrada`, se crea
  automáticamente su `CobranzaFactura` (1:1, confirmado en la spec — no cambió con
  ADR-064). `FacturaClienteService.timbrar()`, en el mismo punto donde ya invoca
  `OrdenClienteService.marcar_facturada()`, invoca también
  `CobranzaFacturaService.crear_para_factura(factura, usuario)` — misma transacción,
  idempotente.
- **Al cancelar**: `FacturaClienteService.cancelar()` invoca
  `CobranzaFacturaService.eliminar_o_rechazar()` ANTES de tocar el estado de la factura.
  Si ya tiene `CobranzaFactura` con `importe_cobrado > 0` (ya se recibió algún pago), la
  cancelación se **rechaza** con `400 error_dominio` — mismo criterio que la excepción de
  "OC ya cobrada" de ADR-047. Si `importe_cobrado = 0`, la `CobranzaFactura` se elimina y
  la cancelación continúa con normalidad.
- **Al completarse el cobro (aprobado en E.1, ver ADR-072)**: cuando
  `CobranzaFactura.estatus_cobro` llega a `cobrada` (`importe_cobrado >= total_factura`,
  recalculado al crear o borrar un `PagoCliente`), la cascada sube: `CobranzaFacturaService.
  recalcular_tras_pago()` invoca `FacturaClienteService.marcar_cobrada()`, que a su vez
  invoca `OrdenClienteService.marcar_cobrada()` para TODAS las órdenes de la factura —
  cierra el ciclo que F2 dejó anticipado (`EstadoFacturacion.COBRADA`/`EstatusOrden.
  COBRADA` ya existían en los enums, sin una transición real que los alcanzara). Sin
  reversa: borrar un `PagoCliente` que dejaría la `CobranzaFactura` por debajo del total
  estando ya `cobrada` se rechaza con `409` (mismo principio de ADR-047, un nivel más
  abajo). El detalle del ancla provisional de `fecha_estimada_cobro` (se crea con
  `fecha_timbrado`, se recalcula al entregar con `fecha_entrega_factura`) está en ADR-072.

## Entidades (spec BD v2, con las 3 desviaciones aditivas de esta sesión)

### CobranzaFactura (14 campos spec, con 2 ajustes + 2 campos nuevos ADR-225/ADR-226)
PK `cobranza_id`. FK `FacturaCliente` (1:1), `anunciante_id` (derivado de la factura),
`metodo_pago_id` — **incoherencia de spec, mismo caso que `FacturaCliente.metodo_pago_clave`
en F2**: no existe tabla `MetodoPago` propia (vive en `ConstantesSistema`), así que este
campo se implementa igual, como `metodo_pago_clave` (texto, sin FK formal).
`dias_credito` (sugerido de `Anunciante.dias_credito_default`, editable).
`fecha_estimada_cobro = FacturaCliente.fecha_entrega_factura + dias_credito` (calculado).
**ADR-225 (petición del usuario):** `agencia_id` (nullable, derivado de
`FacturaCliente.agencia_id` al crear — mismo criterio que `anunciante_id`) — hace falta
para filtrar "facturas pendientes de esta agencia" en el picker de pago múltiple.

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

**ADR-226 (petición del usuario) — columnas "Agencia" y "Número de parcialidad" en la
lista:** `CobranzaFacturaRead` gana `ultimo_numero_pago` (derivado en lectura, NUNCA
columna — mismo criterio que `importe_cobrado`): el `numero_pago` del `PagoCliente` más
reciente de la cobranza, ordenado por `fecha_pago_cliente` desc (la fecha real del pago,
no cuándo se capturó), con `created_at` desc como desempate (p.ej. dos renglones del
mismo pago múltiple, misma fecha). `None` si todavía no hay pagos o el último no lo
capturó. El frontend (`CobranzaFacturasPage.tsx`) agrega la columna "Agencia" (resuelta
con el mismo combo `useAgenciasInfo` que ya usaba el picker de pago múltiple) y "Núm.
parcialidad" (este campo tal cual) al DataTable de la lista — ningún cambio de pantalla
en Facturación.

**ADR-277 (petición del usuario) — adeudo vencido del anunciante, consumido por F1:**
nuevo método `CobranzaFacturaService.adeudo_vencido(anunciante_id)` — suma
`importe_pendiente_cobro` de TODAS las `CobranzaFactura` de ese anunciante que estén
VENCIDAS, reusando el MISMO criterio del badge `vencida` de arriba (`estatus_cobro !=
'cobrada'` y `fecha_estimada_cobro < hoy`), fila por fila (volumen chico por
anunciante, sin consulta agregada). Nuevo endpoint `GET /cobranza/anunciantes/
{anunciante_id}/adeudo-vencido` (`router_adeudo_anunciante`, permiso `cobranza:leer`) →
`{anunciante_id, tiene_adeudo_vencido, suma_adeudo_vencido}`. Vive aquí (F3), no en
Catálogos/Órdenes, porque "vencida" es una noción propia de este módulo. Consumido por
`OrdenClienteService._pre_create` (F1) para BLOQUEAR el alta de una `OrdenCliente` si el
adeudo vencido supera `Anunciante.monto_maximo_credito` (cuando está capturado y es
`> 0`), y por `OrdenClienteForm.tsx` para una alerta no bloqueante al elegir el
anunciante. Detalle completo (incluidas las preguntas abiertas que quedaron fuera de
este alcance: edición vs. alta, override por rol, deuda vía agencia, si el tope debe
sumar también la orden en curso) en `docs/arquitectura.md` (ADR-277) y
`docs/modulos/f1-ordenes/f1-00-ordenes.md`.

**Ajuste posterior (petición del usuario):** en `RegistrarPagoForm.tsx` (pago
individual), "Número de pago" pasa de texto libre a CALCULADO y de solo lectura —
cantidad de `PagoCliente` ya registrados para esa cobranza + 1 (conteo, no se parsea el
texto libre del último, que podría no ser numérico). El pago múltiple no cambia: sigue
siendo texto libre, porque reparte un solo pago entre varias facturas con historiales
distintos y no hay un "siguiente" único que calcular ahí.

**ADR-281 (petición del usuario, con captura) — columnas "Fecha de pago"/"Fecha de
aplicación", orden por fecha de pago y pago individual oculto:** `CobranzaFacturaRead`
gana `fecha_pago`/`fecha_deposito` (derivados en lectura, nunca columnas — mismo
criterio que `ultimo_numero_pago` de ADR-226): `fecha_pago_cliente`/`fecha_deposito` del
`PagoCliente` MÁS RECIENTE de la cobranza, mismo criterio de "último" que
`ultimo_numero_pago` (orden por `fecha_pago_cliente` desc, `created_at` desc como
desempate); `None` en cualquiera de las dos si todavía no hay pagos. `_info_pagos()`
ahora devuelve 4 valores en vez de 2 (misma consulta). La columna de la lista "Fecha de
aplicación" (nombre de negocio pedido para esa columna) mapea a `fecha_deposito`;
"Fecha de pago" mapea a `fecha_pago_cliente`. El orden de la lista pasa de solo
`fecha_estimada_cobro` a `[fecha_estimada_cobro, <fecha del último pago>]` — el
desempate se resuelve con una subconsulta escalar correlacionada a `PagoCliente` (vive
en la tabla hija), pasada directo en `default_order_by`. La búsqueda de esta lista
sigue siendo 100% client-side (mismo límite de siempre, ver ADR-233/241 para "Pagos
recibidos") y ahora también compara contra estas 2 fechas, en ISO crudo y en el formato
de pantalla ("dd-mmm-aa"). Además, las etiquetas de `PagoMultipleForm.tsx` estaban
INVERTIDAS respecto a `RegistrarPagoForm.tsx` (bug de JSX, el `state`/payload interno
siempre mapeó bien) — se homologaron a "Fecha del pago"/"Fecha de depósito" en ambos
formularios. Y se agregó `MOSTRAR_PAGO_INDIVIDUAL = false` en
`CobranzaFacturasPage.tsx` (mismo patrón que `MOSTRAR_BOTON_VER_EN_COBRANZA` de F2) para
ocultar el botón "+ Registrar pago": todos los pagos se capturan ahora por Pago Múltiple,
aunque sea de una sola factura; el formulario y el endpoint individuales siguen
existiendo, solo se ocultó el botón. Detalle completo en `docs/arquitectura.md`
(ADR-281).

**ADR-284 (petición del usuario, con captura) — la búsqueda cubre TODAS las columnas:**
la búsqueda de esta lista (sigue 100% client-side, ver arriba) antes solo comparaba
contra factura/anunciante/fecha de pago/fecha de aplicación — ahora compara contra las
12 columnas visibles de la tabla sin excepción: también Agencia, Días cr., Fecha
estimada (cruda + "dd-mmm-aa"), Total, Cobrado, Pendiente, Estado (etiqueta legible) y
Parcialidad, más el término "Vencida" cuando aplica el badge. El orden
(`fecha_estimada_cobro` + fecha del último pago, ADR-281) no cambió. Detalle completo en
`docs/arquitectura.md` (ADR-284).

### PagoCliente (10 campos spec + 5 campos nuevos ADR-225)
PK `pago_cliente_id`. FK `CobranzaFactura` (N:1, **NULLABLE desde ADR-229** — ver abajo).
Captura manual por **CxC**. `metodo_pago_clave` (mismo ajuste que arriba — texto, no FK).
Al crear/borrar un `PagoCliente`, el servicio recalcula `CobranzaFactura.estatus_cobro`
y `fecha_cobro` (salvo que no tenga cobranza asignada — ver ADR-229).

**ADR-229 (petición del usuario) — "Pagos no asignados":** un pago puede capturarse SIN
elegir factura todavía (`cobranza_id = NULL`) y asignarse después. 3 endpoints nuevos:
`POST /cobranza/pagos/no-asignados` (crea sin cobranza, sin recálculo), `GET /cobranza/
pagos/no-asignados` (lista los `cobranza_id IS NULL`), `POST /cobranza/pagos/{id}/
asignar` (le pone `cobranza_id` y SÍ dispara `recalcular_tras_pago` — puede dejar la
factura `cobro_parcial`/`cobrada`; rechaza con 409 si ya estaba asignado). `eliminar()`
borra un pago sin asignar directo, sin los guardarraíles de "ya cobrada" (no aplica, no
hay cobranza). Frontend: pill "No asignados" + botón "+ Pago sin asignar"
(`PagoSinAsignarForm.tsx`, sin "Número de pago" ni tope contra pendiente) en "Pagos
recibidos"; el detalle de un pago sin asignar muestra un combo + botón "Asignar" en vez
de "Factura aplicada".

**ADR-230 (petición del usuario) — "pago de menos" + repartir un huérfano con Pago
Múltiple:** en Pago Múltiple, si el monto total no se cubre por completo con las
facturas seleccionadas, el SOBRANTE ya no se pierde: `crear_multiple()` lo guarda como
su propio huérfano (mismo `pago_multiple_id`). `PagoMultipleCreate.pago_origen_id`
(nuevo, opcional): si se está REPARTIENDO un huérfano ya existente (no capturando
dinero nuevo), ese huérfano se borra en la MISMA transacción. Frontend:
`PagoMultipleForm.tsx` acepta `origenHuerfano` (precarga sus datos, bloquea "Monto
total del pago"); botón "Repartir con Pago Múltiple" en el detalle de un huérfano
(`PagosClientePage.tsx`), junto al "Asignar" de ADR-229.

**ADR-231 (petición del usuario, reportado con captura) — "Asignar" con monto
parcial:** "Asignar" ya NO le asigna el monto COMPLETO del huérfano a la factura sin
importar su pendiente. `PagoAsignarFacturaRequest.monto_aplicado` (nuevo, obligatorio):
si cubre el huérfano completo, reutiliza la misma fila (igual que antes); si es MENOR,
`asignar()` hace split — crea un `PagoCliente` nuevo solo por lo asignado (con su
propia parcialidad) y el huérfano ORIGINAL se queda con el restante, más chico. Rechaza
con 400 si excede el monto del huérfano (restricción dura); el tope contra el pendiente
de la factura es solo del frontend (mismo criterio que ADR-227). Frontend: "Asignar"
gana un input "Monto a asignar", precargado con el menor entre el pendiente de la
factura y lo que queda del huérfano, editable.

**ADR-233 (petición del usuario) — búsqueda de "Pagos recibidos" por fecha,
referencia, factura o monto:** la caja de búsqueda solo comparaba contra
`referencia_pago`; ahora también compara contra la fecha y el monto YA FORMATEADOS
(como se ven en la tabla), el monto crudo y el número de factura de la cobranza. Solo
cambia el filtro en memoria de `PagosClientePage.tsx`, sin tocar la API.

**ADR-241 (petición del usuario) — el buscador también cubre el número de pago
(parcialidad):** faltaba `numero_pago` (columna "Número de parcialidad") en el filtro
de ADR-233. Se agrega al mismo arreglo comparado; placeholder actualizado a "Buscar
pago, referencia, factura, fecha o monto…".

**ADR-234 (petición del usuario, con captura) — la referencia sube al encabezado del
detalle de un pago:** en vez de ir hasta abajo de "Datos del pago" con el tamaño normal,
la referencia ahora se muestra en el encabezado del panel, a la derecha y al mismo nivel
que el monto, en negrita (15px/700) para que se note de inmediato.

**ADR-235 (petición del usuario, reportado con captura) — "Pago Múltiple del
Anunciante" ya no mezcla facturas de la agencia:** `CobranzaFactura.anunciante_id`
nunca es NULL (es el anunciante DE LA ORDEN, no a quién se factura), así que filtrar
solo por `anunciante_id` dejaba pasar también las facturas de ese anunciante
facturadas a su agencia. `CobranzaFacturaRepository._apply_filters` ahora exige además
`agencia_id IS NULL` cuando la petición NO trae `agencia_id` explícito (mismo criterio
que el selector de "Listas para facturar" de F2). El filtro por `agencia_id` no
cambió — ya era correcto. Límite conocido anotado aquí: una orden directa con
`agencia_id` de referencia seguiría viéndose como "de agencia" — **resuelto el mismo
día, ver ADR-236 abajo: no era un caso raro, era el bug real.**

**ADR-236 (petición del usuario, reportado con captura) — `facturado_directo`
reemplaza `agencia_id IS NULL`:** `agencia_id` es solo una referencia capturada en la
orden — no distingue "a quién se factura" (eso solo lo sabe
`OrdenCliente.facturacion_directa_cliente`). Se agrega `facturado_directo: bool` a
`CobranzaFactura` (y a `FacturaCliente`, calculado igual que `_receptor_de()` de F2,
copiado al timbrar) — `_apply_filters` ahora usa `facturado_directo = True/False` en
vez de `agencia_id IS NULL`/`agencia_id = Y`, en AMBOS modos del picker de Pago
Múltiple. Migración `2e0c8a75aad5` + backfill `4f286d68a07f`.

**ADR-256 (petición del usuario, "NEW FEATURE") — checkbox "Pagado en sistema
externo":** mismo criterio que `FacturaCliente.facturado_en_sistema_externo` (ADR-248,
F2) — nuevo campo `pagado_en_sistema_externo: bool` (default `False`) en `PagoCliente`,
disponible tanto en el pago individual (`RegistrarPagoForm.tsx`) como en el pago
múltiple (`PagoMultipleForm.tsx`, viaja a CADA `PagoCliente` del lote incluido el
huérfano por sobrante). Solo IDENTIFICA el pago — sin ningún efecto en el flujo ni en
los cálculos. Migración `7b931c7fdb4e`.

**ADR-270 (petición del usuario, "Correcciones en pagos múltiples", con
desarrolladores consultados) — el pago ya no puede quedar de más ni de menos:** nueva
columna `ajuste` (DECIMAL, -$10 a +$10) en `PagoCliente`, SOLO del pago múltiple —
se SUMA a `monto_aplicado` (que sigue siendo el pendiente de la factura, sin tocar) al
validar `crear_multiple()`. `suma_asignada = Σ(monto_aplicado + ajuste)` nunca puede
exceder `monto_total_pago`. Si queda por debajo, originalmente (hasta ADR-273, ver
abajo) solo se rechazaba cuando la diferencia cabía dentro del ajuste (≤$10); una
diferencia mayor seguía el huérfano de ADR-230.

`ajuste` NO afecta `importe_cobrado`/`importe_pendiente_cobro` de la factura (siguen
basados solo en `monto_aplicado`) — es una corrección contra lo CAPTURADO (comisión
bancaria, redondeo), no contra la factura. `PagoMultipleItemCreate.ajuste` (Pydantic,
`ge=-10, le=10`, default 0); columna con CHECK `ajuste BETWEEN -10 AND 10`, default 0 —
0 en todo pago individual (no se captura ahí). Frontend: `PagoMultipleForm.tsx` agrega
la columna "Ajuste" a la tabla de facturas disponibles (ancho máximo de 6 caracteres,
ej. "-10.00", sin redondear sus 2 decimales), editable solo si la factura está marcada;
"Monto asignado"/"Monto por asignar" ahora incluyen el ajuste; mismo guardarraíl de 3
casos en vivo (botón deshabilitado) que ADR-227. Migración `e6f7a8b9c0d1`.

**ADR-273 (petición del usuario, "Correcciones en pagos múltiples — parte 2") — el
pago múltiple ya NUNCA puede quedar por debajo del monto total, sin importar la
diferencia:** se quita de `crear_multiple()` la parte de ADR-230/270 que toleraba una
diferencia MAYOR a $10 generando un huérfano con el sobrante — ahora CUALQUIER
`suma_asignada < monto_total_pago` se rechaza (400), haya que seleccionar más facturas,
subir los montos aplicados, o cuadrar con la columna de Ajuste. Repartir un huérfano
existente (`pago_origen_id`) también debe cubrir su monto COMPLETO, sin dejar un
sobrante más chico (antes `asignar()`/ADR-231 sí lo permitía vía split; ESE endpoint no
cambió, solo `crear_multiple`). El mecanismo de huérfano (`PagoCliente.cobranza_id =
NULL`) sigue existiendo para otros flujos (`/pagos/no-asignados`, `/asignar`,
ADR-229/231) — solo se quitó la creación automática desde Pago Múltiple. Además:
- Columna "Número de Parcialidad"/"Núm. parcialidad" renombrada a **"Parcialidad"** en
  las 3 tablas donde aparecía (`PagoMultipleForm.tsx`, `PagosClientePage.tsx`,
  `CobranzaFacturasPage.tsx`).
- Nuevo contador "Ajuste" en el tablero de montos de `PagoMultipleForm.tsx` (4a
  tarjeta, ancho angosto ~6 caracteres): suma en vivo de todos los ajustes capturados.
- Bug corregido: `fmtMoneda` (`modules/cobranza/format.ts`) anteponía el signo de
  "menos" al símbolo de moneda ("-$0.70"); ahora va DESPUÉS ("$-0.70") — afecta
  cualquier monto negativo mostrado con esta función (p.ej. "Monto por asignar",
  `diferencia_afiliada` en Requisiciones).
No hay migración nueva (no cambia el esquema, solo la validación y la UI).

**ADR-271 (petición del usuario, "Cancelación de Pago", con desarrolladores
consultados) — "Pagos recibidos" se reestructura y se agrega cancelación:**

- **La tabla principal deja de listar por factura y pasa a listar por PAGO GLOBAL.**
  Antes: una fila por cada `PagoCliente` aplicado a una `CobranzaFactura` (si un pago
  múltiple cubría 3 facturas, 3 filas). Ahora: una fila por pago (todas las filas que
  comparten `pago_multiple_id`, o la única fila si es individual) — columnas Fecha,
  Referencia, Monto (el total del pago, no de la factura), Factura (cantidad cubierta),
  Estatus (Pagado/Cancelado). Se deja fuera, a propósito, "Estatus Timbrado" (pedido
  explícito del usuario: no es prioridad todavía).
  - Se decidió NO crear una entidad nueva ("pago global" como tabla propia): `PagoCliente`
    sigue exactamente igual (evaluado y descartado — ver conversación — reestructurar a
    tabla padre + aplicaciones hubiera significado migrar TODOS los pagos históricos, alto
    riesgo sobre algo ya probado). El "pago global" es una vista/consulta agrupada nueva
    (`PagoClienteService.listar_agrupado`/`detalle_agrupado`, `GET /pagos` y
    `GET /pagos/{id}/detalle`), agrupando por `coalesce(pago_multiple_id, pago_cliente_id)`.
  - `monto_pago`/`total_pago` se RECONSTRUYEN sumando `monto_aplicado + ajuste` de TODO el
    grupo (incluido el "huérfano" sin asignar de ADR-230 si existe) — nunca se persiste:
    por el invariante que ya garantiza `crear_multiple` (ADR-230/270), esa suma siempre da
    exacto el monto que de verdad se capturó.
  - Detalle de un pago: sus facturas aplicadas (número, parcialidad, monto aplicado SIN
    el ajuste — el ajuste no toca la factura) + el total real al final.
- **Nuevo botón "Cancelación de Pago"** (reemplaza "Eliminar" en el detalle de "Cobranza
  de facturas", que se QUITA — los pagos ya aplicados solo se cancelan desde "Pagos
  recibidos"): cancela TODO el pago global de una sola vez. Columna nueva `estatus_pago`
  (`pagado`/`cancelado`) en `PagoCliente` — **baja LÓGICA, ya no física** para un pago
  ASIGNADO (cambia ADR-035: ese criterio sigue aplicando SOLO a un pago sin asignar,
  `eliminar()` ahora rechaza con 400 si el pago ya tiene `cobranza_id`). `importe_cobrado()`
  excluye los pagos `cancelado` de la suma — con solo ese filtro, cancelar reutiliza TAL
  CUAL la máquina de `recalcular_tras_pago` que ya existía (crear/asignar/crear_multiple):
  la factura baja de `cobrada`/`cobro_parcial` a `pendiente`/`cobro_parcial` sola.
- **Regla de negocio simplificada (decisión del usuario, más segura que el guardarraíl
  preexistente de `eliminar()`):** si CUALQUIERA de las facturas que toca el pago YA está
  `cobrada`, la cancelación se RECHAZA con 409 — sin excepción, sin importar si ese pago
  en particular era "extra"/prescindible o no. Con esta regla, **nunca** hace falta
  construir una reversa hacia `FacturaCliente`/`OrdenCliente` (que no existía — ver ADR-047
  y el docstring de `cobranza_factura.py`): la cascada de 3 pasos sigue siendo de un solo
  sentido, intacta. Cancelar un pago múltiple cancela TODAS sus filas a la vez (incluido el
  huérfano sin asignar de ese mismo lote, si existe).
- Migración `f1a2b3c4d5e6` (columna + CHECK). Endpoints nuevos: `GET /pagos` (agrupado),
  `GET /pagos/{id}/detalle`, `POST /pagos/{id}/cancelar` (permiso `cobranza:editar`, 204).

**ADR-286 (petición del usuario, con captura) — reemplaza la regla "ciega" de ADR-271;
ver la entrada completa en `arquitectura.md`:** el usuario reportó que cancelar un pago
que cubre varias facturas fallaba con el mensaje de "nota de crédito" — investigando se
confirmó que la regla de ADR-271 bloqueaba igual para 1 o N facturas (un pago múltiple
solo tiene más probabilidad de tocar una ya `cobrada`). Pedido explícito: **sí** debe
poder cancelarse aunque eso deshaga una orden/factura ya `cobrada`, con **motivo
obligatorio** (columna nueva `pago_cliente.motivo_cancelacion`, migración `5782aa74d8d8`).
Resumen del cambio (detalle técnico completo en `arquitectura.md`):
- `PagoClienteService.cancelar` ya NO rechaza por "ya cobrada" — en vez de eso,
  `CobranzaFacturaService.recalcular_tras_pago` detecta la transición hacia atrás y
  dispara `FacturaClienteService.revertir_cobro` → `OrdenClienteService.revertir_cobro`
  (gemelos hacia atrás de `marcar_cobrada`, mismo patrón de handoff sin `commit` propio).
- Lo único que SÍ bloquea (validado ANTES de tocar cualquier fila, todo-o-nada sobre el
  grupo completo): que alguna orden ya tenga una `FacturaAgencia`/`FacturaVendedor`/
  `FacturaAfiliado` autorizada o pagada con base en que estaba `cobrada`
  (`comisiones_comprometidas_de_orden` en `factura_cliente.py`) — eso sí es un compromiso
  tomado que ya no se puede deshacer limpiamente.
- `POST /pagos/{id}/cancelar` ahora exige body `{"motivo": "..."}` (`min_length=3`).
- `PagoGrupoDetalleRead`/`PagoClienteRead` exponen `motivo_cancelacion`.

**ADR-288 (F2, petición del usuario, con captura) — Notas de Crédito aplicadas como
`PagoCliente` sintético; ver la entrada completa en `arquitectura.md` y en
`docs/modulos/f2-facturacion/f2-facturacion.md`:** una Nota de Crédito
(`FacturaCliente.tipo_comprobante == "E"`) NO es una entidad de F3 ni tiene su propia
`CobranzaFactura` — al timbrarse, `PagoClienteService.aplicar_nota_credito` inserta un
`PagoCliente` más sobre la `CobranzaFactura` de la factura que acredita, marcado con la
columna nueva `factura_egreso_id` (FK a la NC, `UNIQUE` — se aplica una sola vez).
`metodo_pago_clave` siempre `PUE`, `numero_pago` siempre `"1"` (la NC cuenta como la
primera parcialidad, nunca se calcula con `_info_pagos`), `referencia_pago` = el folio
de la NC (para identificarla sola en "Pagos recibidos"). `importe_cobrado()`/
`recalcular_tras_pago()` no se tocaron: ya suman cualquier `PagoCliente` `pagado`, sin
importar su origen. Cancelar la NC (`PagoClienteService.revertir_nota_credito`) reutiliza
completo ADR-286 (`_cancelar_sin_commit` — la versión pública `cancelar()` se separó del
`commit` para poder componerse dentro de la transacción de
`FacturaClienteService.cancelar`).

**ADR-225 — "Pago Múltiple para varias facturas" (petición del usuario):** un pago
recibido puede repartirse entre varias facturas del MISMO anunciante o agencia — cada
factura seleccionada se registra como su propio `PagoCliente` (no hay tabla puente N:M
nueva: `PagoCliente→CobranzaFactura` ya era N:1, así que "un pago, varias facturas" es
simplemente varios `PagoCliente`, cada uno con su propio `monto_aplicado`).
- `metodo_pago_clave` pasa a **NULLABLE**: el pago múltiple no lo captura (no se pidió
  para ese flujo); el pago individual lo sigue exigiendo vía `PagoClienteCreate`
  (Pydantic), no por la columna.
- 5 columnas nuevas, agregadas TANTO al pago individual como al múltiple (petición
  explícita): `forma_pago_clave` (clave de `ConstantesSistema` grupo `FormaPago` —
  REUTILIZA el catálogo que F2 ya usa para `FacturaCliente.forma_pago_clave`, sin FK
  formal, mismo patrón que `metodo_pago_clave`), `fecha_deposito`, `numero_pago` (texto
  libre en el pago múltiple, tipo "2 de 3", sin fórmula — en el pago INDIVIDUAL, ADR-226
  lo calcula y lo precarga de solo lectura, ver abajo), `cuenta_contable_id` (FK real a
  `CuentaContable`, catálogo ya existente — reutilizado de F2 también), `pago_multiple_id`
  (UUID compartido por todos los `PagoCliente` de una misma captura múltiple, indexado,
  para trazabilidad — `NULL` en un pago individual).
- Nuevo endpoint `POST /cobranza/pagos/multiples` (`PagoMultipleCreate`): captura además
  `monto_total_pago` (lo que de verdad entró — puede ser MAYOR a la suma de `pagos`,
  asignación parcial permitida) y la lista `pagos` (`cobranza_id` + `monto_aplicado` por
  factura). Valida que la suma asignada no exceda `monto_total_pago` y que ninguna
  factura se repita en el mismo lote; TODO o NADA en una sola transacción (si cualquier
  renglón falla, se revierte lo ya insertado). **NO topa** cada `monto_aplicado` contra
  el pendiente de SU factura individual — mismo criterio que el pago sencillo, que nunca
  lo hizo (`recalcular_tras_pago` ya tolera un pago de más, dejando la factura `cobrada`
  igual).
- Frontend: `CobranzaFacturasPage.tsx` gana un botón "+ Pago múltiple" que despliega
  `PagoMultipleForm.tsx` a pantalla completa DENTRO de la misma pantalla (no una ruta
  nueva) — mismo patrón de checkbox mutuamente excluyente "por Anunciante"/"por Agencia"
  que ADR-064/ADR-201 ya usa en F2, con un tablero en vivo de Monto total/Monto
  asignado/Monto por asignar. El flujo de pago individual (`RegistrarPagoForm.tsx`) no
  cambió de pantalla, solo ganó los 4 campos nuevos de arriba.

### Requisicion (23 campos spec + `factura_vendedor_id` agregado — ver ADR-216)
PK `requisicion_id`. `tipo_requisicion` ENUM (`pago_afiliado`/`pago_agencia`/
`comision_vendedor`/`comision_agencia` — en la UI, `comision_vendedor` se muestra como
**"Pagos vendedor"** desde ADR-219, el valor interno no cambia; **`comision_agencia` ya
NO aparece en el selector del alta desde ADR-220**, aunque sigue existiendo en el
modelo/API para lo ya capturado). FKs según el tipo (`factura_afiliado_id`,
`factura_agencia_id`, `factura_vendedor_id`, `orden_id`, `afiliado_id`, `agencia_id`,
`vendedor_comision_id`) — **`factura_afiliado_id`/`factura_agencia_id`/
`factura_vendedor_id` son OBLIGATORIAS** para sus respectivos tipos desde ADR-219/
ADR-220 (antes eran opcionales: se podía capturar la requisición sin saber todavía a
cuál factura correspondía). `comision_agencia` no tiene ninguna factura asociada (pago
puro de comisión, confirmado por diseño — no aplica cierre de factura) y sigue siendo
el único tipo con `orden_id` + % de comisión (ya inalcanzable desde el alta, ADR-220).
Captura por **CxP**. Calculados: `requisicion_comision_vendedor = OrdenCliente.total *
porcentaje_comision_vendedor / 100` — **ya NO se ejecuta para altas nuevas de
`comision_vendedor`** desde ADR-219 (no hay `orden_id` del que tomarlo); las columnas
siguen existiendo, solo quedan sin capturar por esa vía. `requisicion_comision_agencia`
análogo, SIN cambios. `diferencia_afiliada = monto_requisicion -
FacturaAfiliado.total_factura_afiliado` (monitoreo de márgenes, puede ser negativa — no
llevar `CHECK >= 0` en ese campo).

**Máquina de estados real** (con endpoint dedicado, mismo mecanismo de seams que F1/F2):
`pendiente → autorizada → pagada`, rama a `cancelada` desde `pendiente`/`autorizada`.
**Autorización**: el paso `pendiente→autorizada` requiere **Dirección o Admin** (mismo
canal dedicado del ADR-046 — permiso de router en `pagos:leer`, chequeo de área real
dentro del servicio) — CxP captura pero no se autoriza a sí mismo. Extensión directa del
patrón ya aprobado en F2. **ADR-283:** `pago_afiliado`/`pago_agencia`/`comision_vendedor`
ya NO nacen en `pendiente` — nacen directo en `autorizada` (ver más abajo), así que para
estos 3 tipos el único paso de la máquina de estados que de verdad se recorre en la
práctica es `autorizada → pagada`/`cancelada`. `comision_agencia` es la única excepción:
sigue naciendo en `pendiente` y recorriendo la máquina completa.
**Efecto colateral al pagar (ADR-216):** al llegar a `pagada`, la Requisicion cierra
también (`.transicionar(..., "pagada", ...)`) la `FacturaAfiliado`/`FacturaAgencia`/
`FacturaVendedor` que tenga enlazada por FK, siempre (sin verificar si existen otras
requisiciones pendientes sobre la misma factura — decisión explícita del usuario).

**Combos "disponibles" del alta clásica (ADR-217):** `GET /cobranza/requisiciones/facturas-
{afiliado,agencia,vendedor}-disponibles` — facturas `autorizada` que NINGUNA
`Requisicion` (de cualquier estatus) tiene ligada todavía; reemplazan, para el alta de
Requisicion, el pedir directo `/facturacion/afiliados|agencias|vendedores` (ese listado
genérico de Facturación sigue mostrando TODAS las facturas, sin este filtro). **ADR-282:**
desde que el alta de `pago_afiliado`/`pago_agencia`/`comision_vendedor` se movió al
bloque embebido en su propia pantalla de Factura (F2 — ver más abajo), estos 3 combos ya
no los usa ningún formulario del frontend (la factura se conoce por contexto); se dejan
intactos (siguen probados) por si se necesitan de nuevo, no se borraron.

**ADR-282 (petición del usuario, con captura) — folio automático, validación reforzada
y reubicación del alta:**
- **Folio automático:** `numero_requisicion` dejó de capturarse a mano —
  `RequisicionCreate` ya no tiene ese campo (`extra="forbid"`, mandarlo da 422). Se
  genera siempre en `RequisicionService._siguiente_numero_requisicion()`, mismo patrón
  que el folio de `OrdenCliente` (ADR-237/254/275): `RQ-AAAA-MM-consecutivo`,
  consecutivo GLOBAL (no reinicia por año/mes), sin padding, escaneando el máximo
  existente por regex en vez de una secuencia de BD.
- **Validación de elegibilidad reforzada:** antes, que una factura ya estuviera "usada"
  o no estuviera `autorizada` solo lo filtraban los combos "disponibles" de arriba — el
  propio `create()` no lo exigía. Como el alta embebida en Facturación ya no pasa por
  esos combos, se agregó `RequisicionService._validar_factura_disponible()`: 400
  `error_dominio` si la factura no está `autorizada`, 409 `conflicto` si ya tiene otra
  Requisicion ligada. Aplica a los 3 tipos con factura de origen; `comision_agencia` no
  tiene factura, no aplica.
- **Columna/búsqueda "Folio":** `RequisicionRead` expone `folio_factura_origen`
  (resuelto en lote por página en el servicio, `_enriquecer_folios()` — mismo patrón por
  lote que `_conteo_asignaciones` de F2, evita N+1 contra las 3 tablas posibles); `null`
  para `comision_agencia`. `q` ahora también busca ese folio (`EXISTS` correlacionado
  contra `FacturaAfiliado`/`FacturaAgencia`/`FacturaVendedor`, ya que una requisición
  solo trae UNA de las 3 FKs a la vez). En el frontend, la columna que antes se llamaba
  "Origen" (resuelta en el cliente con catálogos `xxxInfo`, con una limitación conocida
  si la factura ya no estaba en ese lote) se renombró a "Folio" y usa directo este campo.
- **"Requisiciones de pago" pasa a ser CONSULTA, salvo "Comisión agencia":** el botón de
  alta de `RequisicionesPage.tsx` ahora dice "+ Nueva comisión de agencia" y solo crea
  ese tipo — es el único sin factura de origen (es un pago sobre una `OrdenCliente`
  directamente), así que sigue siendo el único que se da de alta aquí. Para los otros 3
  tipos, el alta vive en su propia pantalla de Factura (F2): `RequisicionInlineForm.tsx`,
  un componente **del módulo `facturacion`** (no de `cobranza`) — decisión de
  arquitectura: el proyecto ya tenía la dependencia unidireccional `cobranza →
  facturacion` (en ambas capas), así que el componente embebido vive del lado de
  Facturación, con un tipo y una función de API LOCALES y mínimos
  (`RequisicionDesdeFacturaCreate`/`crearRequisicionDesdeFactura()` en
  `facturacion/types.ts`/`api.ts`, que pegan directo a `/cobranza/requisiciones`) en vez
  de importar nada del módulo `cobranza`. `RequisicionForm.tsx` (el formulario clásico de
  esta pantalla) se simplificó: ya no tiene selector de "Tipo de requisición" ni los
  bloques de los otros 3 tipos, solo Agencia + Orden de cliente + % Comisión + Monto +
  OC SAP + Observaciones.

**ADR-283 (petición del usuario, con captura) — la requisición nace ya autorizada si
viene de una factura:** antes, generar la Requisicion desde el bloque embebido de
Facturación (ADR-282) dejaba la nueva fila en `pendiente`, obligando a Dirección a
"Autorizar →" de nuevo en "Requisiciones de pago" — redundante, porque la
`FacturaAfiliado`/`FacturaAgencia`/`FacturaVendedor` de origen YA tuvo que estar
`autorizada` para poder generarla (`_validar_factura_disponible`, ADR-282). Ahora
`RequisicionService.create()` calcula `tiene_factura_origen` (si trae
`factura_afiliado_id`/`factura_agencia_id`/`factura_vendedor_id`) y arranca el registro
directo en `autorizada` cuando es así — en la pantalla, el botón "Autorizar →" ya no
aparece para estos 3 tipos, solo "Cancelar"/"Marcar pagada →". `comision_agencia` (sin
factura de origen, nada la autorizó antes) sigue naciendo en `pendiente` y pasando por
el canal de autorización normal — única excepción. No cambió la máquina de estados ni
los endpoints `/estatus`/`/autorizar`, solo el estatus INICIAL del alta.

**Badge "Orden de servicio" del detalle (ADR-218, actualizado en ADR-219):** junto al
estado/tipo, mismo patrón que el badge de orden en Facturas de Cliente (ADR-064) —
folio + `+N` si hay varias. Resuelto en el frontend con los catálogos ya cargados:
`comision_agencia` vía `orden_id` directo (el único que lo sigue capturando);
`pago_agencia` y `comision_vendedor` (desde ADR-219) vía la factura ligada
(`FacturaAgencia.orden_id` / `FacturaVendedor.orden_id`); `pago_afiliado` reusa el
endpoint de asignaciones de F2 (`GET /facturacion/afiliados/{id}/ordenes`, con
`folio_orden` agregado) para resolver la(s) Orden(es) de Servicio detrás de una factura
repartida en parcialidades.

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

## Roles / permisos — Tesorería (resuelto, ver ADR-073)

Este es el primer módulo donde **Tesorería pasa de "solo lectura" a "captura"**
(`MovimientoBancario`). Se resolvió con el mismo canal dedicado del ADR-046 (ya usado
para la autorización de Dirección): los endpoints de `MovimientoBancario` piden
`pagos:leer` en el router (nivel que Tesorería ya tenía) y el servicio verifica
`área in (TESORERIA, ADMIN)` antes de escribir. Tesorería NO tiene `pagos:editar` en la
matriz — si lo tuviera, también podría capturar `Requisicion`, que la ficha reserva
para CxP.

## Dependencias

- F2 completo (`FacturaCliente` timbrada, `FacturaAfiliado`/`FacturaAgencia` autorizadas).
- F0 completo (`Anunciante.dias_credito_default`, `ConstantesSistema` para métodos de
  pago, `Afiliado`/`Agencia`/`Vendedor`). F5-00 (RBAC real).

## Frontend (`frontend/src/modules/cobranza/`)

Mismo patrón que F2 (types → api → hooks → format/constants → components → pages →
registry → explorador), montado en `/cobranza` (`phase-f3`, ámbar) con 4 grupos de
sidebar exactos al mockup aprobado: "Cobranza al cliente" (Cobranza de facturas, Pagos
recibidos), "Pagos a proveedores" (Requisiciones), "Tesorería" (Movimientos bancarios) y
"Vistas operativas" (Cobranzas vencidas, Por autorizar, Por pagar, Sin conciliar — las 4
son las MISMAS páginas con un filtro inicial preseleccionado, no pantallas nuevas).

- **Deep-link F2→F3**: el botón "Pasa a CxC (Fase 3)" de `FacturasClientePage` (antes un
  placeholder deshabilitado) ahora navega a `/cobranza?factura_id=...` y
  `CobranzaFacturasPage` resuelve y preselecciona la `CobranzaFactura` correspondiente —
  coherente con que ya existe desde `timbrada` (ADR-072), no solo desde `entregada`.
- **Limitaciones conocidas de esta tanda** (no bloquean, documentadas en el propio
  código): el backend no indexa texto libre ni el badge `vencida` sobre
  `CobranzaFactura` — la búsqueda y la vista "Vencidas" traen hasta 100 filas y filtran
  en el cliente. Tampoco hay un `GET` de "todos los pagos" — el historial de "Pagos
  recibidos" se arma agregando por cobranza (mismo tope de 100).
- **21 pruebas de componente** (Vitest + Testing Library) en `CobranzaFacturasPage.
  test.tsx` y `RequisicionesPage.test.tsx`: qué botones ofrece la UI en cada estado
  (mismo criterio que F2, no lo que el backend ya valida).
- Edición de `Requisicion` vía `PUT` (backend completo) **no se expuso** en esta tanda:
  el formulario cubre alta; editar montos/comisiones se deja para cuando se necesite.

## Pendientes (no bloquean el arranque de F3)

- **`ExtractoBancarioPort`** (puerto+adaptador para carga de estados de cuenta por
  archivo): NO se construyó — la captura MANUAL de `MovimientoBancario` no depende de
  él (ver el plan aprobado) y cubre el flujo del mockup. Se construye cuando llegue el
  formato real, mismo patrón que `TimbradoExportPort` (ADR-048).
- Si el negocio pide matching automático de conciliación más adelante, es una extensión
  sobre `MovimientoBancario`, no un rediseño.
- Migración `19395aa1c258` (regenerada tras rebasar sobre `main` con spots bonificables
  de F1 — la original `4235d887cf06` quedó huérfana y se eliminó) NO aplicada a RDS
  todavía (4 tablas nuevas, ninguna existente tocada; también corrige condicionalmente
  la deriva preexistente de índices en `constantes_sistema`/`contrato`/`marca` cuando el
  dialecto es SQL Server) — pendiente de tu confirmación antes de aplicarla, como con
  toda migración.
