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
`estatus_orden = orden_cerrada`. Es 1:1 (spec): una OC genera como máximo una factura de
cliente. Si no se cumple, `400 error_dominio`.

## Entidades (spec BD v2, con 2 desviaciones aditivas aprobadas)

### FacturaCliente (33 campos spec, con 2 ajustes)
PK `factura_id`. FKs a `OrdenCliente` (1:1), `FacturaCliente` (self-FK, para notas de
crédito/complementos — nullable), `EmpresaFacturadora`/`Anunciante`/`Agencia` (heredados
de la OC), `CuentaContable` (F0-05, ya existe). Derivados de la OC: razón social/RFC/
dirección de facturación, fechas de transmisión, `subtotal_factura`. Calculados:
`iva_factura = subtotal_factura * 0.16`, `total_factura = subtotal_factura + iva_factura`.

**Ajuste 1 — `layout_factura_id` → `layout_factura` (texto libre).** El catálogo
`LayoutFactura` nunca se construyó en F0. Se reemplaza el FK `NOT NULL` por un campo de
texto libre (nullable), sin catálogo por ahora — extensión aditiva documentada, a
revisar si el negocio pide más de una plantilla real en el futuro.

**Ajuste 2 — `metodo_pago_id` → `metodo_pago_clave` (texto).** `MetodoPago` no es tabla
propia: vive dentro de `ConstantesSistema` (grupo `FormaPago`/`MetodoPago`, ya construido
en F0-05). Se guarda la **clave** directamente (ej. `"03"`, `"PUE"`), sin FK formal —
el frontend puede seguir sugiriendo desde `ConstantesSistema` para poblar el combo, pero
la relación no se valida a nivel de base de datos.

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
varias facturas de agencia, a diferencia de `FacturaCliente` que es 1:1). Captura manual
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
