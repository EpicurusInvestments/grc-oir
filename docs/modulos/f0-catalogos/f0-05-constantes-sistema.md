# Módulo F0-05 — Constantes del sistema (catálogos SAT / timbrador) · Fase: F0

> Pantalla "Constantes del sistema": catálogos del SAT y configuración del timbrador
> externo que **consume Facturación (F2)**. Solo lectura para los operadores; edición
> restringida al administrador. Referencia: `Fase_0_-_Catalogos.html` (grupo "constantes").
> Es el **último módulo de la Fase 0**.

## Propósito

Centralizar los valores fiscales válidos que el sistema usará al **preparar** las
facturas para el timbrador externo (recordar: el sistema NO timbra). Son los valores
que el operador podrá elegir en las pantallas de facturación (F2).

## Entidad / modelo

Una entidad de configuración tipo "constante" — `ConstantesSistema` — con: `id` (PK),
`grupo` (a qué catálogo pertenece), `clave` (el valor), `descripcion`, `valor` (opcional,
p.ej. legacy "33"), `activo`, `created_at`, `updated_at`.

### Grupos SAT/timbrador (de la pantalla)
- **TipoComprobante** — Tipo de comprobante CFDI (I, E, P; "33" legacy del timbrador).
- **Serie** — Serie de la factura.
- **RegimenFiscal** — Régimen fiscal SAT.
- **ClaveProdServ** — Clave de producto/servicio SAT.
- **ClaveUnidad** — Clave de unidad SAT.
- **UsoCFDI** — Uso del CFDI.
- **FormaPago** — Forma de pago SAT.
- **MetodoPago** — Método de pago SAT.
- **MonedaSAT** — Moneda.

### Grupos absorbidos desde F0-04 (decisión del equipo)
- **MetodoPago** (ya listado arriba como catálogo SAT) — se gestiona aquí, NO como tabla
  propia (se difirió de F0-04).
- **CuentaContable** — catálogo contable interno (código de cuenta, nombre, tipo:
  ingreso/costo/gasto/activo/pasivo). Se difirió de F0-04 y se gestiona aquí dentro de
  `ConstantesSistema`. `[[POR CONFIRMAR: ver "Decisión de modelado" abajo — CuentaContable
  tiene campos propios (codigo, nombre, tipo) que no encajan igual que una constante
  SAT simple; hay que decidir cómo se modela dentro de ConstantesSistema.]]`

## Decisión de modelado pendiente (importante)

Las constantes SAT son homogéneas (grupo + clave + descripción + valor). Pero
**CuentaContable** tiene una estructura algo distinta (código de cuenta, nombre de cuenta,
tipo de cuenta con ENUM). Hay que decidir en el plan cómo conviven:
- Opción 1: `ConstantesSistema` genérica con un campo flexible (p.ej. el `tipo_cuenta` va
  en `valor` o en un campo extra) — más simple, menos estricto.
- Opción 2: `ConstantesSistema` para lo SAT + tabla `CuentaContable` aparte para lo
  contable (recupera lo que se difirió de F0-04) — más limpio semánticamente.
El plan debe proponer y justificar. (Nota: MetodoPago SÍ encaja bien como constante SAT
simple; el que genera la duda es CuentaContable.)

## Estados
- Solo `activo`. Filtrado por grupo y búsqueda por clave/descripción/grupo.

## Pantallas (de la pantalla F0)
- Lista con **filtros por grupo** (pills con conteo por grupo) y badge **"Solo lectura"**
  en el encabezado. Para el operador es consulta; el alta/edición es solo del Admin.
- **Captura de datos: manual Y masiva (CSV).** El Admin puede:
  - Agregar/editar registros manualmente (uno por uno).
  - **Importar de forma masiva** un archivo CSV (o similar) exportado de un portal
    oficial u otro sistema, para dar de alta muchos registros a la vez.
- Subtítulo: indica que estos valores alimentan las pantallas de Facturación (F2).

## Carga masiva (CSV) — funcionalidad NUEVA en el proyecto

- El Admin sube un archivo CSV con los registros a importar.
- El sistema valida el archivo (formato, columnas esperadas, filas inválidas) ANTES de
  insertar, y reporta al usuario qué se importó y qué se rechazó (con el motivo).
- Considerar: manejo de duplicados (¿omitir, actualizar, o rechazar?), tamaño máximo de
  archivo, y que la validación sea clara. `[[El plan debe proponer el detalle de esta
  funcionalidad — es la primera vez que el proyecto maneja importación de archivos.]]`

## Roles / permisos
- **Lectura:** todas las áreas operativas.
- **Edición (manual y carga masiva):** Admin (IT) únicamente por ahora. Más adelante se
  podrá definir si otro rol asume esta responsabilidad (se afinará en F5).

## Reglas de negocio clave
- Estos catálogos NO se editan en operación normal; cambian poco y de forma controlada.
- Los valores deben corresponder a los catálogos oficiales del SAT vigentes (CFDI 4.0).
- **Origen de los datos (confirmado):** captura **manual** (uno por uno) **y masiva**
  (archivo CSV/similar exportado de un portal oficial u otro sistema).

## Carga inicial (confirmado)
- **Inicialmente la carga será MANUAL.** Aún no se tiene una lista formal con todos los
  catálogos del SAT; cuando se tenga, se procederá con una carga (probablemente masiva vía
  CSV). Por ahora NO se hace seed automático de los catálogos SAT.

## Actualización cuando el SAT cambia (confirmado)
- **Quién:** por ahora el **Admin (IT)**. Más adelante podría definirse otro rol
  responsable (se verá en F5).
- **Frecuencia:** no es periódica; se actualiza **cuando haya cambios** — nueva regulación
  o ley fiscal, disposición interna, o necesidad de agregar/actualizar catálogos. Es un
  proceso reactivo, no programado.

## Integraciones
- Indirecta: estos valores se usan al **preparar el archivo plano** para el timbrador
  externo (módulo de F2). No hay llamada a servicios aquí.
- La carga masiva CSV es procesamiento de archivo local (no una integración externa).

## Dependencias
- F0-00 (fundamentos). Conviene tenerlo listo antes de iniciar F2 (F2 consume estos valores).

## Decisiones confirmadas (respuestas del equipo)
1. **Origen de datos:** captura manual + carga masiva vía CSV/similar.
2. **Carga inicial:** manual por ahora (no seed automático); carga masiva cuando exista la
   lista formal del SAT.
3. **Actualización:** el Admin la hace, de forma reactiva (cuando cambia la normativa o por
   disposición interna). Otro rol podría asumirlo en F5.
4. **MetodoPago y CuentaContable** (diferidos de F0-04): se gestionan en este módulo (ver
   "Decisión de modelado pendiente" sobre cómo modelar CuentaContable).

## Pendientes / dudas (para resolver en el plan)
- Cómo modelar CuentaContable dentro de/junto a ConstantesSistema (ver "Decisión de modelado").
- Detalle de la carga masiva CSV: columnas esperadas por grupo, manejo de duplicados,
  validación y reporte de resultados.