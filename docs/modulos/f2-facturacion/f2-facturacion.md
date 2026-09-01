# Módulo F2 — Facturación · Fase: F2

> **Estado: REFINADA — lista para generar el plan con Claude Code.**
> Ficha de alcance de TODO el módulo `facturacion` (las 5 entidades se implementan juntas
> por su acoplamiento: FacturaCliente es el centro; FacturaAfiliado/FacturaAgencia/
> CostoAdicional dependen de ella o de la OC). Mismo criterio que F1, que terminó
> construyéndose como un solo módulo consolidado por la misma razón.
> Referencias: spec BD v2, `CLAUDE.md` (mapa de módulos, convenciones, máquinas de
> estado), `docs/arquitectura.md` (ADR-002 no-timbrado, ADR-019 estados independientes,
> ADR-030/034/042 patrones ya usados en F1, ADR-039 aritmética de dinero, ADR-040 RBAC).
> Refinada en sesión de planeación del [[fecha]], tras confirmar que F0+F1+F5-00 ya están
> en `main`.

## Propósito

Tomar las Órdenes de Cliente que F1 dejó en `orden_cerrada` y preparar su factura —
**el sistema NUNCA timbra** (ADR-002): arma toda la información, la exporta para un
timbrador externo (PAC), y registra lo que ese PAC devuelve (folio fiscal, XML, PDF).
En paralelo, registra las facturas que OIR *recibe* de afiliados y agencias (costos), y
costos adicionales de nómina/overhead — todo lo que alimentará el Estado de Resultados
de F4 y las Requisiciones de pago de F3.

## Precondición de alta

Solo se puede generar una `FacturaCliente` para una `OrdenCliente` cuyo
`estatus_orden = orden_cerrada`. Si no se cumple, `400 error_dominio`.

La relación es **N:M** desde ADR-064 (desviación de la spec autorizada por el equipo): una
factura puede cubrir varias órdenes cerradas del mismo anunciante, y vive en la tabla
puente `factura_cliente_orden`. Lo que sigue vigente es que una OC **no puede estar en dos
facturas vigentes** (las canceladas no cuentan, ADR-047); con la columna `orden_id` se fue
el índice que lo garantizaba, así que ahora lo valida el servicio con `409`.

### Facturación múltiple

El alta recibe `ordenes_ids`. Con **una** orden es el flujo de siempre; con **varias**, el
servicio exige que compartan **empresa facturadora**, **anunciante** y **receptor** — un
CFDI tiene un solo emisor y un solo receptor, así que mezclarlos es imposible de timbrar.
El receptor se compara como par `(tipo, id)` y no por `agencia_id`: dos órdenes de la misma
agencia pueden diferir en `facturacion_directa_cliente`, y entonces una se factura a la
agencia y la otra al anunciante.

De las órdenes incluidas se calcula:

| Campo | Regla |
|---|---|
| `subtotal_factura` | suma de los `subtotal` de las órdenes |
| `iva_factura` / `total_factura` | sobre esa suma, como siempre (16 %) |
| `fecha_inicio_transmision` | la más temprana de las órdenes |
| `fecha_fin_transmision` | la más tardía |

Se suman **subtotales**, no totales: sumar importes que ya traen IVA violaría los CHECK
`ck_factura_cliente_iva_calculado` y `ck_factura_cliente_total_suma`.

#### La pantalla

La bandeja "Listas para facturar" tiene dos modos. El **normal** factura una orden por
tarjeta. Al marcar **«Facturar Múltiples Órdenes»** aparecen, en el orden en que se
trabaja: el combo **«Seleccionar Anunciante»** (con búsqueda; solo lista anunciantes con 2
o más órdenes disponibles) y el botón **«Generar Factura Múltiple»** a su derecha.

Mientras no se elija anunciante la bandeja no lista nada: muestra la invitación a elegirlo,
porque listar todas las órdenes en modo múltiple invitaría a marcar órdenes de anunciantes
distintos que el backend va a rechazar. Al elegirlo, las tarjetas se acotan a ese anunciante
y cambian su acción: en vez de «Generar factura →» llevan la casilla **«Incluir en la
factura»**. La tarjeta marcada se distingue por borde y fondo, no solo por su casilla.

El botón **no se deshabilita** con menos de dos órdenes marcadas: valida al hacer clic y
explica qué falta («Selecciona al menos 2 órdenes… Llevas 1»). Un botón muerto sin
explicación deja al usuario adivinando.

El formulario de alta es el mismo (`FacturaClienteForm`), con una prop `ordenes`: muestra
los folios y pedidos concatenados, el periodo consolidado y el **subtotal sumado**, que es
lo que calculará el servicio. Desmarcar el check devuelve todo al modo normal.

#### «Órdenes relacionadas» en el panel de detalle

El panel de *Facturas al cliente* abre con el timeline y las tres tarjetas de importes, y
justo después lleva la sección **«Órdenes relacionadas»** (tag *Derivado*): una fila por
orden con folio, número de pedido del cliente, periodo y **su** subtotal. Con más de una
cierra con el resumen «N órdenes · suma de subtotales».

Se muestra **siempre**, también en facturas de una sola orden: una sección que aparece y
desaparece obliga a recordar por qué, y con una orden la respuesta sigue siendo útil. Si no
hubiera ninguna, lo dice en vez de dejar el hueco.

El badge del encabezado sigue siendo el identificador corto: el folio de la **primera**
orden y, si cubre varias, cuántas más (`OC-2025-0051 +1`). El detalle está en la sección.

Los datos llegan resueltos en la misma respuesta (`ordenes`), sin una consulta por renglón.

Al timbrar, el handoff con F1 promueve **todas** las órdenes a `facturada`; al cancelar,
las revierte todas. Si cualquiera está en `cobrada`, la cancelación entera se rechaza con
**400** y no quedan órdenes revertidas a medias.

En el archivo del PAC va **una sola línea de detalle consolidada** (decisión del equipo),
con los folios y números de orden concatenados por coma. El producto solo se emite si todas
las órdenes coinciden; si difieren, cae a `descripcion_factura`.

## Entidades (spec BD v2, con 2 desviaciones aditivas aprobadas)

### FacturaCliente (33 campos spec, con 3 ajustes)
PK `factura_id`. Órdenes que cubre vía `factura_cliente_orden` (**N:M**, ADR-064 — la spec
las ligaba con `orden_id` 1:1). FKs a `EmpresaFacturadora`/`Anunciante`/`Agencia`
(heredados de la OC), `CuentaContable` (F0-05, ya existe). Derivados de la OC: razón
social/RFC/dirección de facturación, fechas de transmisión, `subtotal_factura`.
Calculados: `iva_factura = subtotal_factura * 0.16`,
`total_factura = subtotal_factura + iva_factura`.

**Ajuste 1 — `layout_factura_id` → `layout_factura` (texto libre).** El catálogo
`LayoutFactura` nunca se construyó en F0. Se reemplaza el FK `NOT NULL` por un campo de
texto libre (nullable), sin catálogo por ahora — extensión aditiva documentada, a
revisar si el negocio pide más de una plantilla real en el futuro.

**Ajuste 2 — `metodo_pago_id` → `metodo_pago_clave` (texto).** `MetodoPago` no es tabla
propia: vive dentro de `ConstantesSistema` (grupo `FormaPago`/`MetodoPago`, ya construido
en F0-05). Se guarda la **clave** directamente (ej. `"03"`, `"PUE"`), sin FK formal —
el frontend puede seguir sugiriendo desde `ConstantesSistema` para poblar el combo, pero
la relación no se valida a nivel de base de datos.

**Ajuste 3 — `factura_relacionada_id` (self-FK único) → tabla N:N
`factura_cliente_relacionada` (ADR-062).** La pantalla de "Nueva factura" necesitaba
poder marcar VARIAS facturas del mismo anunciante como relacionadas (control de
sustituciones/canceladas, no solo un CFDI previo), y CFDI 4.0 admite varios
`CfdiRelacionado` bajo un mismo `TipoRelacion` — así que la cardinalidad de la spec se
amplió de 1 a N. `FacturaClienteCreate.facturas_relacionadas_ids: list[UUID]`; el combo
del frontend (`MultiSearchableSelect`) se filtra por `anunciante_id` de la orden y
muestra también las facturas canceladas a propósito (es el control que pidió negocio).

**Máquina de estados propia** (`estado_facturacion`, ya predefinida en `CLAUDE.md`):
```
preparada → enviada_a_timbrado → timbrada → entregada → cobrada
                                                        ↘ cancelada (desde los 4 primeros)
```
`folio_fiscal_sat`, `fecha_timbrado`, `xml_path`, `pdf_path`: NULL hasta timbrar; se
llenan al pasar a `timbrada` (vía el mismo endpoint genérico de adjuntos que F1, ver
"Adjuntos" abajo, para XML/PDF).

### FacturaAfiliado (13 campos spec)
PK `factura_afiliado_id`. FK a `Afiliado`. Captura manual o carga de archivo, por **CxP**
(no Facturación — ver RBAC). `total_factura_afiliado` calculado
(`monto + iva`). Estados: `recibida → en_revision → autorizada → pagada`.

### FacturaAfiliadoOrden (5 campos spec)
Relación N:M `FacturaAfiliado` ↔ `OrdenEstacion` **cerrada** — permite repartir el costo
de una factura del afiliado entre varias OE. `monto_asignado` + `notas_asignacion`.

### FacturaAgencia (15 campos spec)
PK `factura_agencia_id`. FK a `Agencia` y a `OrdenCliente` (**1:N** — una OC puede tener
varias facturas de agencia; `FacturaCliente` es N:M desde ADR-064). Captura manual
o carga, por **CxP**. `porcentaje_comision_agencia` sugerido desde el catálogo Agencia
(editable), `comision_agencia = OrdenCliente.total * porcentaje / 100` calculado. Mismos
4 estados que `FacturaAfiliado`.

### CostoAdicional (10 campos spec)
PK `costo_id`. `tipo_costo` ENUM (`nomina`/`overhead`). FK a `OrdenCliente` **nullable**
(NULL = costo general, no ligado a una venta). Captura por **CxP**. Sin máquina de
estados — es un registro simple.

## Cálculos (siempre en el servicio, nunca aceptados del cliente)

- `FacturaCliente`: `iva_factura = subtotal_factura * 0.16`; `total_factura = subtotal +
  iva`. `Decimal`, nunca float (ADR-015).
- `FacturaAfiliado`/`FacturaAgencia`: `total_* = monto_* + iva_*`.
- `FacturaAgencia.comision_agencia = OrdenCliente.total * porcentaje_comision_agencia /
  100`.
- **Advertencia de ADR-039 (aplica desde el día 1 aquí):** cualquier `CHECK` de
  **igualdad** entre montos calculados por separado debe envolverse en `ROUND(x, 2)` en
  ambos lados — SQLite (desarrollo local) guarda `NUMERIC` como `float64` y una suma
  puede fallar por 1 ULP de ruido aunque la aritmética `Decimal` real sea exacta. F2 va
  a tener más aritmética de dinero que F1; no esperar a que la re-siembra lo descubra.

## El "handoff" con F1 — regla de sincronización (nueva, se define aquí)

`OrdenCliente.estatus_orden` pasa de `en_verificacion` a `facturada` **cuando
`FacturaCliente.estado_facturacion` llega a `timbrada`** (confirmado en sesión de
planeación) — no antes (con solo `preparada`/`enviada_a_timbrado` la OC se queda en
`en_verificacion`), ni se espera a `entregada`. Mecanismo: el servicio de F2, al mover
una factura a `timbrada`, debe invocar internamente la transición de la OC (mismo patrón
que F1-02 usó para promover la OC de `capturada`→`en_transmision` al derivar OI) — **no**
un nuevo endpoint HTTP, una llamada de servicio a servicio.

`OrdenCliente.estatus_orden = cobrada` es responsabilidad de **F3**, no de F2 — F2 no
lo toca.

## Exportación del archivo plano — hueco de negocio conocido, diseño aislado

El formato real que espera el PAC sigue **sin definirse** (`[[POR LLENAR]]` desde el
inicio del proyecto). Para no bloquear el resto del módulo:
- Construir un **puerto de exportación** (`TimbradoExportPort`, mismo patrón que el
  puerto de almacenamiento S3/ADR-020) con un adaptador **placeholder** que genera un
  archivo de texto con los campos ya conocidos de `FacturaCliente` en un formato
  simple y explícitamente marcado como **borrador, no el formato real del PAC**.
- Cuando llegue la especificación real, se reemplaza solo el adaptador — el resto del
  flujo (estado `preparada→enviada_a_timbrado`, captura de respuesta) no cambia.
- Dejar esto anotado como pendiente crítico a resolver antes de ir a producción, no
  antes de continuar desarrollando.

## Adjuntos

Reutilizar el mismo patrón genérico de F1 (ADR-042: `documentos.py`, lista blanca de
extensiones + magic bytes), extendiéndolo con nuevos `tipo` para: XML/PDF del CFDI
timbrado (`FacturaCliente`), y el archivo cargado de `FacturaAfiliado`/`FacturaAgencia`/
`CostoAdicional`. No se replica el CRUD completo de Contrato — mismo criterio que F1.

## RBAC (confirmado en sesión)

| Entidad | Quién captura | Quién solo lee |
|---|---|---|
| `FacturaCliente` | Facturación | Ventas, Tesorería, CxC, CxP, Dirección, Nóminas |
| `FacturaAfiliado`, `FacturaAgencia`, `CostoAdicional` | CxP | Facturación, Ventas, Tesorería, CxC, Dirección, Nóminas |

Admin es superusuario automático en todo módulo (ADR-040) — **no listarlo
explícitamente** en la matriz, ya lo resuelve `_nivel()`.

**Autorización confirmada:** el paso `en_revision→autorizada` de `FacturaAfiliado`/
`FacturaAgencia` lo ejecuta **Dirección o Admin** (mismo criterio que la edición de
comisiones post-cierre en F1) — no el propio CxP que capturó el registro.

## Convenciones técnicas obligatorias (de los ADRs de F1, aplican igual aquí)

- Infra CRUD genérica desde `app/shared/` (ADR-032), no reimplementar ni importar de
  `catalogos/`.
- Columnas de fecha/hora/texto largo con `fecha_sql()`/`hora_sql()`/`texto_largo()` de
  `core/db.py` (ADR-036) — nunca `sa.Date()`/`sa.Time()`/`sa.UnicodeText()` a secas.
- Máquinas de estado con el mismo mecanismo de seams ya usado en F1 (transiciones
  explícitas, endpoint dedicado, 409 en transición inválida, idempotente en mismo
  estado).
- PKs UUID, nombres snake_case en español tal cual la spec, `created_at`/`updated_at`/
  `created_by`.

## Integraciones

- **Timbrador externo (PAC)**: salida (archivo plano placeholder) / entrada (folio
  fiscal, XML, PDF) — ver sección de exportación arriba.
- Ninguna otra en esta fase.

## Dependencias

- F1 completo (OC en `orden_cerrada`, OE cerradas). F0 completo (Afiliado, Agencia,
  EmpresaFacturadora, CuentaContable, ConstantesSistema). F5-00 (autenticación real y
  RBAC por área ya en producción).

## Pendientes (no bloquean el arranque de F2)

- Formato real del archivo plano del PAC (ver sección dedicada arriba).
- Catálogo `LayoutFactura` real, si el negocio termina necesitando más de una plantilla.
  Mientras no exista, el campo está OCULTO en el alta y el detalle de "Facturas al
  cliente" (era texto libre sin guía — ver ADR-054); el modelo lo conserva.

## Estado de implementación

- **Tanda 1 (modelo + migración + lectura) — COMPLETA.** Las 5 entidades como tablas
  reales (`factura_cliente`, `factura_afiliado`, `factura_afiliado_orden`,
  `factura_agencia`, `costo_adicional`) en la migración `3e57e45d24cb`, encadenada a
  `a1c8e3d47b92` (F5-00). Ninguna tabla de F0/F1 se toca. 9 endpoints `GET` con
  paginación, filtros propios y búsqueda de texto. RBAC con las dos claves del ADR-044.
  Verificado: **334/334 pytest** (31 nuevas), `ruff`/`mypy` limpios sobre el módulo, SQL
  offline de `mssql` regenerado (0 `NTEXT`, 0 `DATETIME` espurio, 7 `DATE`, 8
  `DATETIME2`, 5 `NVARCHAR(max)`), y ciclo `downgrade`/`upgrade` completo contra la
  SQLite local. **No aplicada a RDS todavía.**
  - Los 4 CHECK de igualdad de montos llevan `ROUND(x, 2)` en ambos lados desde el primer
    día (ADR-039), con prueba de que un centavo de diferencia SIGUE siendo rechazado.
    Solo `FacturaCliente` lleva además el CHECK de `iva = subtotal * 0.16`: en las
    facturas de proveedor el IVA es capturado (spec: "Manual"), puede traer retenciones o
    exentos, e imponerle la tasa rechazaría facturas legítimas.
  - Las 2 UNIQUE (1:1 de `factura_cliente.orden_id` y la compuesta de
    `FacturaAfiliadoOrden`) están probadas por ambos lados: que el duplicado falla y que
    el caso legítimo pasa (varias facturas de agencia por OC; la misma OE repartida entre
    facturas de afiliado distintas). **Nota (ADR-064):** la primera de esas dos
      UNIQUE ya no existe — la relación pasó a N:M y la regla vive ahora en el servicio.
  - **Hallazgo (ADR-045):** el CHECK de formato de `periodo_contable` se escribió primero
    con `LIKE '[0-9]...'` (T-SQL) y SQLite lo rechaza todo, incluido el valor válido. Se
    cambió a `LIKE '____-__'`, portable. Lo encontró la prueba, no la revisión visual.
  - **Hallazgo colateral (fuera de F2):** `migrations/env.py` no importaba
    `constantes_sistema` ni `cuenta_contable`, así que cualquier `--autogenerate` habría
    emitido un `drop_table` de dos tablas ya aplicadas a RDS. Se agregaron los imports.
    La deriva de índices que el autogenerate reportó sobre `constantes_sistema`,
    `contrato` y `marca` se eliminó a mano de la migración de F2 (es preexistente y ajena
    a esta fase) y queda como ticket aparte.

- **Tanda 2 (escritura + máquinas de estado + handoff + puerto de timbrado) — COMPLETA.**
  17 endpoints en total (9 de lectura + 8 de escritura/transición) más el de adjuntos.
  **No requirió tocar el esquema**: `alembic check` confirma 0 operaciones pendientes de
  F2 (todo estaba previsto en la migración de la Tanda 1). Verificado: **355/355 pytest**
  (21 nuevas), `ruff`/`mypy` limpios sobre el módulo.
  - **Handoff con F1 implementado y probado.** `FacturaClienteService.timbrar` invoca
    `OrdenClienteService.marcar_facturada` — método NUEVO y aditivo en F1, el único cambio
    a `app/modules/ordenes/` — con la misma sesión y antes del commit. Las pruebas cubren:
    que `preparada` y `enviada_a_timbrado` NO mueven la orden, que `timbrada` sí la deja en
    `facturada`, que repetir el timbrado es idempotente, y que **si la OC no admite la
    transición el timbrado se revierte entero** (atomicidad).
  - **Cancelar una factura NO revierte la OrdenCliente.** Deshacer `facturada` es una
    decisión de negocio que nadie ha tomado; se dejó explícito en el código y en la prueba
    en vez de inventar un comportamiento. Ver pendientes.
  - **Puerto de timbrado** (`app/integrations/timbrado/`): `TimbradoExportPort` + un
    adaptador **placeholder** cuyo archivo lleva la advertencia *"FORMATO BORRADOR - NO ES
    EL LAYOUT REAL DEL PAC - NO ENVIAR A TIMBRAR"* en la primera línea. Una prueba verifica
    esa marca: si alguien escribe el adaptador real reutilizando el placeholder, falla.
    Deliberadamente NO imita un layout posicional ni un CFDI — un archivo que aparenta ser
    el formato real es peor que uno que evidentemente no lo es.
  - **Hallazgo (ADR-046):** la matriz de la ficha (CxP captura, Dirección solo lee) y la
    regla de autorización (Dirección autoriza) se contradicen si ambas pasan por el mismo
    endpoint: el permiso de módulo bloqueaba a Dirección antes del chequeo de área. Se
    separó `POST /{id}/autorizar` como canal dedicado con permiso de router `costos:leer`,
    igual que el canal de comisiones de F1. Lo encontró una prueba parametrizada.
  - **XML agregado a la lista blanca de adjuntos** (capa de integración compartida), sin
    ampliar en silencio lo que acepta F1: las listas por módulo ahora son explícitas.
- **Tanda 5 (layout real del PAC) — COMPLETA.** Llegó el ejemplo de producción del
  archivo plano y se implementó el adaptador real (**ADR-048**), eliminando el placeholder.
  - Estructura MEDIDA sobre el archivo: 20 secciones, CRLF, valor en la columna 17 (19 en
    `AGREGADOS`), detalle posicional de 17 columnas. Una prueba **regenera la fila de
    detalle del ejemplo byte a byte**; otra compara las 20 secciones y sus campos. Con una
    sola muestra, esa es la única evidencia dura de que el layout está bien.
  - Lo que el modelo no puede llenar se emite VACÍO y se reporta en la cabecera
    `X-Campos-Faltantes`, que la pantalla pinta como advertencia al descargar. **No se
    inventan valores fiscales**: un `ClaveProdServ` equivocado produce un CFDI que timbra
    y está mal, peor que uno que no timbra.
  - **Hallazgo (ADR-049):** al generar el primer archivo contra la base REAL, el export
    reventó — 16 columnas FK de F2 habían quedado en `NullType` porque una `ForeignKey`
    sin tipo explícito hereda el tipo de la columna referida, y esa tabla aún no estaba
    importada. Devolvían `str` en vez de `uuid.UUID`. **Las pruebas no lo veían** porque
    escriben y leen en la misma sesión, sin pasar por la base. Corregido con tipo explícito
    en las 16 y una prueba que falla si alguna columna queda sin tipo.
  - Verificado: **376/376 pytest** (11 nuevas del layout), archivo real generado desde la
    demo (5 407 bytes, 9 campos faltantes listados).

- **Tanda 4 (reversión del handoff al cancelar) — COMPLETA.** Decisión de negocio del
  equipo, documentada en **ADR-047**. Cancelar una factura devuelve la `OrdenCliente` de
  `facturada` a `orden_cerrada`, y el 1:1 pasa de `UNIQUE` a **índice único FILTRADO**
  (`WHERE estado_facturacion <> 'cancelada'`) para que esa orden pueda facturarse de
  nuevo sin borrar el registro de la cancelada.
  - `OrdenClienteService.revertir_facturacion()` — segundo y último toque a F1, gemelo
    hacia atrás de `marcar_facturada()`: sin `commit` propio, invocado desde F2 en la
    misma transacción.
  - **La regla se expresa por el estado de la ORDEN**, no por el de la factura:
    `facturada` → revierte; `cobrada` → **400** (requeriría nota de crédito, fuera de
    alcance); cualquier otro → no hace nada. Así quedan cubiertos sin enumerarlos tanto
    cancelar desde `preparada`/`enviada_a_timbrado` (el handoff nunca ocurrió) como desde
    `entregada`, que la redacción inicial de la decisión no mencionaba pero sí requiere
    reversión.
  - **Portabilidad verificada, no supuesta:** SQLite SÍ soporta índices parciales (desde
    3.8) y SQLAlchemy emite el mismo DDL para SQL Server y SQLite, así que no hizo falta
    una validación de unicidad de respaldo en el servicio. Lo que sí se ajustó es el
    chequeo que devuelve el 409 legible, que ahora ignora las canceladas.
  - **La bandeja "Listas para facturar" tuvo que cambiar también**, o la decisión quedaba
    a medias: la orden sería re-facturable pero invisible. El filtro va en la condición
    del `JOIN`, no en el `WHERE` (ahí convertiría el `LEFT JOIN` en `INNER`).
  - La migración `3e57e45d24cb` se editó EN SITIO tras confirmar que no se ha aplicado a
    RDS (`alembic_version = a1c8e3d47b92`, `factura_cliente` inexistente ahí). Ciclo
    `downgrade`/`upgrade` verificado.
  - Se retiró la prueba `test_cancelar_no_revierte_la_orden`, que afirmaba el
    comportamiento anterior y quedó invalidada por esta decisión.
  - Verificado: **364/364 pytest** (6 nuevas), `ruff`/`mypy` limpios, DDL comprobado en
    los dos dialectos.

- **Segunda revisión contra la pantalla aprobada** (capturas comparadas, 2026-08-25). Se
  alinearon las diferencias de formato que quedaban:
  - **Sidebar:** grupos y etiquetas del prototipo — «Facturación al cliente», «Facturas
    recibidas» (De afiliados / De agencias) y «Costos».
  - **Facturas al cliente:** botón «+ Generar factura desde orden cerrada» (no «Nueva
    factura»), subtítulo del prototipo, buscador por número/pedido/razón social, **4
    filtros** (Todas · Pendientes timbrar · Timbradas · Cobradas) en vez de uno por estado,
    y la tabla de **8 columnas** (número, pedido, razón social receptor, empresa emisora,
    fecha, total, folio fiscal —con «— sin timbrar —» cuando falta— y estado).
  - **Panel de detalle:** dejó de ser una lista plana. Abre con los badges de estado y
    receptor, el **timeline** del ciclo de vida (Prep. → Enviada → Timbrada → Entregada →
    Cobrada) y las **tres tarjetas** de Subtotal / IVA / Total, y luego las secciones con
    sus tags de origen. Las acciones usan los textos del prototipo («Marcar enviada a
    timbrado →», «Registrar respuesta del timbrado →», «Marcar entregada →», y el
    «Pasa a CxC (Fase 3)» deshabilitado en `entregada`).
  - **Generar factura:** era un formulario plano; ahora es el *form full-screen* por
    secciones del prototipo — bloque ámbar de **datos heredados de la orden**, y tarjetas
    de Identificación, Receptor (con el aviso de «vía agencia» o «facturación directa»),
    Concepto (con la **descripción pre-cargada**), Montos (Subtotal heredado · IVA y Total
    calculados) , Configuración contable y Fechas.
  - Para que el formulario pueda pre-cargar, la bandeja devuelve además empresa emisora,
    spots, duración y el receptor ya resuelto; y la lista de facturas devuelve el **nombre**
    de la empresa emisora, resuelto en una sola consulta por página (sin N+1).
  - **Una diferencia deliberada con el prototipo:** ahí el **Subtotal** es un input
    editable; aquí es de solo lectura con su tag «Heredado». Es la base de los importes
    calculados y viene de lo que F1 cerró: editarlo rompería la correspondencia entre la
    factura y su orden. El receptor SÍ quedó editable, como el prototipo lo marca.
  - Se agregaron al tema los estilos que faltaban (`.mc-*`, `.heredado-*`, `.form-card`,
    `.receptor-nota`, el token `--amber-border`), portados del prototipo.

- **Ajustes contra la pantalla aprobada** (revisión de `Fase_2_-_Facturacion.html` con
  capturas reales, 2026-08-24):
  1. **Bandeja "Listas para facturar"** (faltaba): ítem propio en el sidebar de Ingresos
     con contador en rojo (`urgent`), endpoint
     `GET /facturacion/ordenes-por-facturar` y pantalla de tarjetas —malla, no tabla, como
     el mockup: cada renglón es una decisión ("¿facturo esta?"), no un dato que se compare
     en columnas. «Generar factura →» REUTILIZA `FacturaClienteForm` con la orden fija (se
     muestra el folio, sin selector), no un segundo formulario en paralelo. El endpoint
     vive en F2 y solo LEE el modelo de F1. Desde la Tanda 4 el `JOIN` ignora las
     facturas canceladas, así que una orden cuya factura se canceló REAPARECE aquí.
     Para que la bandeja sea demostrable se agregó una **11.ª OrdenCliente** a la siembra,
     cerrada y sin factura: la única otra orden cerrada (`oc6`) ya tiene factura sembrada,
     así que la pantalla habría salido siempre vacía.
  2. **Badge «Cobrada»**: era teal y debía ser oscuro. **No hizo falta tocar
     `theme.css`**: la clase `.b-dark` ya es exactamente `background: var(--text)` con
     `--text: #181816` —el mismo valor del mockup— y F1 ya la usa para su propio estado
     `cobrada`. El error estaba en el mapeo de `format.ts`; se corrigió ahí, sin tocar
     ningún otro badge.

- **Tanda 3 (frontend + siembra de demo) — COMPLETA.** Módulo
  `frontend/src/modules/facturacion/` con el patrón de pantalla del proyecto (explorador
  con sidebar + lista y panel de detalle), ruta `/facturacion` y **F2 habilitada** en
  `phaseRegistry.ts` con su acento azul (`.phase-f2`, tokens `--blue`/`--blue-border`
  nuevos en `theme.css`). 4 pantallas: Facturas al cliente, de afiliado, de agencia y
  Costos adicionales.
  - **Las acciones se ofrecen solo cuando la transición es válida** desde el estado
    actual: la UI no muestra un botón que el backend rechazaría con 409. Es UX — el
    servidor valida siempre. Hay pruebas por estado que lo verifican.
  - **El botón «Autorizar» NO se oculta por área.** El front no conoce la matriz RBAC; si
    el área no alcanza, el backend responde 403 y el mensaje se pinta tal cual. Ocultarlo
    daría la falsa impresión de que la acción no existe.
  - El sidebar agrupa en **«Ingresos»** y **«Costos»**, que no es cosmética: refleja las
    dos claves de RBAC del ADR-044 (Facturación captura lo primero, CxP lo segundo).
  - El formulario de "Registrar timbrado" (`RegistrarTimbradoForm.tsx` — pantalla
    completa desde ADR-051, ya no un `Dialog` chico) **avisa explícitamente que la orden
    pasará a `facturada`**, porque el handoff ocurre fuera de la vista de esta pantalla.
    Ahí mismo ya se pueden cargar de verdad el XML y el PDF del CFDI (`AdjuntoFacturaInput`,
    opcionales), conectados al endpoint de adjuntos que ya existía sin usarse. También
    captura `serie_timbrado` (columna aditiva NULL, migración `4f2e15c90f71` — ver ADR-051).
  - El botón «+ Generar factura desde orden cerrada» de «Facturas al cliente» YA NO abre
    un alta embebida (esa rama se eliminó): navega a «Listas para facturar» — el único
    punto de alta real, con la orden ya fija — y se inhabilita cuando esa bandeja está
    vacía (ver ADR-053). El salto entre secciones lo permite un `goTo` nuevo en
    `facturacionRegistry`/`FacturacionExplorerPage`, disponible para cualquier otra
    sección que lo necesite.
  - El detalle de «Facturas al cliente» muestra el folio de la `OrdenCliente` de
    origen como badge en el header (junto al estado y la razón social) — antes solo
    aparecía el número de PEDIDO del cliente (`numero_pedido`), que no es lo mismo.
    `folio_orden` viaja denormalizado en `FacturaClienteRead`, resuelto también tras
    cada transición para que no desaparezca al timbrar/entregar/cancelar (ver
    ADR-055).
  - `hooks.ts`: timbrar invalida ADEMÁS la caché de órdenes (`ordenes`), o la pantalla de
    F1 quedaría mostrando un estado viejo tras el handoff.
  - **Siembra de demo** en `scripts/seed_dev.py`: 4 FacturaCliente (una por estado del
    ciclo), 2 de afiliado con su reparto entre OE cerradas, 2 de agencia y 3 costos, más
    las 3 CuentaContable y las 4 ConstantesSistema que F2 necesita y que la siembra no
    cubría. **Los montos no se inventan**: se derivan de la OC/OE ya sembradas, así que
    los CHECK de suma exacta se cumplen por construcción. Los estados se eligieron para
    respetar la invariante del handoff (una OC está en `facturada` si y solo si su factura
    llegó al menos a `timbrada`) — verificado con una consulta sobre la base sembrada.
  - Verificado: `tsc --noEmit` limpio, `eslint` limpio sobre el módulo, **141 pruebas de
    frontend pasan** (136 + 5 nuevas). Los 19 fallos que quedan son preexistentes y ajenos
    a F2 (`window.localStorage` indefinido con Node 26 frente al Node 20 que fija el
    proyecto), en los mismos 4 archivos de siempre.

## Pendientes / dudas

- ~~Formato real del archivo plano del PAC~~ **RESUELTO** en la Tanda 5 (ADR-048): el
  layout V40 está implementado y verificado contra el ejemplo de producción. Lo que sigue
  abierto es OTRA cosa, ver los dos puntos siguientes.
- **Codificación del archivo plano.** Se asume CP1252 (`TIMBRADO_ENCODING`), pero el
  ejemplo llegó con sus acentos ya corruptos, así que no se pudo deducir del archivo.
  **Confirmar con el PAC antes de producción.**
- **(Resuelto, ADR-061)** Campos fiscales que el modelo no capturaba y el PAC exigía:
  régimen fiscal (ya se resolvía solo con UNA constante activa), serie (ya NO es
  catálogo — se deriva del propio `numero_factura`, ADR-061), `ClaveProdServ`/
  `ClaveUnidad`/`UsoCFDI`/forma de pago SAT (sembrados con valores reales de
  producción, un único activo por grupo). Verificado en vivo: 0 campos faltantes.
  **(Resuelto, ADR-060)** Los domicilios DESGLOSADOS de emisor/receptor y
  `AGREGADOS.LugarExpedicion` (código postal de expedición) ya salen del domicilio
  estructurado por CP de Anunciante/EmpresaFacturadora (ADR-059) — el receptor solo si
  esta factura es de facturación DIRECTA (sin agencia), porque `Agencia` todavía no
  captura domicilio así. La pantalla sigue listando lo que falte al descargar.
- **Catálogo `LayoutFactura` real**, si el negocio termina necesitando más de una
  plantilla (hoy `layout_factura` es texto libre).
- **Deriva de índices en tablas de F0** (ver hallazgo colateral arriba): decidir si se
  corrige con una migración dedicada o si se alinean los modelos a lo que ya existe en
  RDS. `alembic check` sigue reportando esas 3 operaciones (y solo esas).
- ~~¿Cancelar una factura timbrada debe revertir la `OrdenCliente`?~~ **RESUELTO** en la
  Tanda 4 (ADR-047): sí revierte, y el 1:1 pasó a índice único filtrado para permitir
  refacturar. La excepción es una orden ya `cobrada`, que se rechaza con 400 porque
  requeriría una nota de crédito — eso sí sigue fuera de alcance.
- **¿Quién dispara `FacturaCliente → cobrada`?** La transición existe en la máquina pero
  en F2 nadie la invoca; es de F3 (Cobranza), igual que `OrdenCliente → cobrada`.
