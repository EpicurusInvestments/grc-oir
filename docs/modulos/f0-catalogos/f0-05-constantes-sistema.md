# Módulo F0-05 — Constantes del sistema (catálogos SAT / timbrador) · Fase: F0

> **Estado: IMPLEMENTADO** (2026-07, 3 tandas: backend+CRUD manual · carga masiva CSV ·
> frontend). Con este módulo se **cierra la Fase 0** completa.
>
> Pantalla "Constantes del sistema": catálogos del SAT y configuración del timbrador
> externo que **consume Facturación (F2)**. Solo lectura para los operadores; edición
> restringida al administrador. Referencia: `Fase_0_-_Catalogos.html` (grupo "constantes").
> Es el **último módulo de la Fase 0**.

## Qué se construyó (resumen)

- **`ConstantesSistema`** (tabla `constantes_sistema`): entidad de configuración homogénea
  (`grupo`/`clave`/`descripcion`/`valor`) con los 9 grupos SAT/timbrador. Unicidad natural
  `(grupo, clave)` case-insensitive. CRUD manual (Admin) + **carga masiva CSV** con flujo
  *dry-run → confirmar*. Filtro por grupo, conteos por grupo (pills) y búsqueda.
- **`CuentaContable`** (tabla `cuenta_contable`, **tabla propia** — ADR-024): catálogo
  contable con `codigo_cuenta` (único CI), `nombre_cuenta` y `tipo_cuenta` (ENUM). CRUD
  manual simple (sin carga CSV por ahora).
- **`MetodoPago`**: se gestiona como **grupo** de `ConstantesSistema` (valores PUE/PPD).
- Migración `b6d9f2a4c817` (aplicada y verificada contra RDS: CHECK, únicos, tipos).
- Decisiones registradas en **ADR-024** (modelado CuentaContable) y **ADR-025** (carga CSV);
  endpoints en `docs/API-CONTRACT.md` (sección F0-05).

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
- **MetodoPago** (ya listado arriba como catálogo SAT) — se gestiona aquí como **grupo** de
  `ConstantesSistema`, NO como tabla propia (se difirió de F0-04). Valores: PUE/PPD.
- **CuentaContable** — catálogo contable interno (código de cuenta, nombre, tipo:
  ingreso/costo/gasto/activo/pasivo). Se difirió de F0-04 y se implementó como **tabla
  propia** (ver "Decisión de modelado (resuelta)" abajo).

## Decisión de modelado (resuelta) — CuentaContable = tabla propia (ADR-024)

Las constantes SAT son homogéneas (grupo + clave + descripción + valor). **CuentaContable**
tiene estructura propia (código, nombre, `tipo_cuenta` con ENUM). Se evaluaron dos opciones:
- Opción 1: dentro de `ConstantesSistema` genérica (tipo en `valor`) — más simple, menos estricto.
- Opción 2: **tabla `CuentaContable` aparte** — más limpio y fiel a la spec. **← ELEGIDA.**

**Decisión (Opción 2):** tabla propia. Motivos: fidelidad a la spec v2 (regla de oro #3); el
ENUM `tipo_cuenta` se implementa como VARCHAR + CHECK nombrado (imposible sobre el `valor`
genérico compartido por 9 grupos); integridad futura (F3/F4 podrán referenciarla por FK);
costo bajo (otro catálogo sobre la base de F0-00). `MetodoPago` sí encaja como constante SAT
simple. Detalle y consecuencias en **ADR-024**.

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

## Carga masiva (CSV) — funcionalidad NUEVA en el proyecto (IMPLEMENTADA, ADR-025)

Solo para `ConstantesSistema` (Admin). Detalle completo en **ADR-025** y en `API-CONTRACT.md`.

- **Endpoint:** `POST /api/v1/catalogos/constantes/importar` (`multipart/form-data`).
- **Flujo dry-run → confirmar (stateless):** `commit=false` devuelve el reporte de qué se
  haría **sin escribir**; el cliente re-sube el mismo archivo con `commit=true` para aplicar.
  El archivo se procesa en memoria y **NO se persiste** en el servidor.
- **Columnas:** `grupo,clave,descripcion,valor,activo` (encabezado; UTF-8 con/sin BOM;
  delimitador `,` o `;`).
- **Validación en dos niveles:** estructural (columnas faltantes/vacío/no-UTF-8 → 400;
  tamaño/filas → 413) que aborta todo; y por fila (import **parcial**: válidas entran,
  inválidas se reportan con motivo).
- **Duplicados:** `actualizar` (upsert, default, idempotente), `omitir` o `rechazar`;
  duplicado **dentro del archivo** → 2ª fila rechazada. Aplicación **atómica** del subconjunto
  válido (una transacción; rollback total si falla a nivel BD).
- **Límites:** 2 MB / 5 000 filas (configurables en `config.py`). Solo `.csv`. `csv`/`io` de
  la stdlib (sin pandas); única dependencia nueva: `python-multipart`.
- **Reporte:** `{ commit, total_filas, creadas, actualizadas, omitidas, rechazadas,
  errores_estructura, filas[] }` con `estado` por fila ∈ creada|actualizada|omitida|rechazada.
- **Helper reutilizable** `importacion_csv.py`: CuentaContable u otros catálogos podrán sumar
  carga CSV reusándolo (hoy no lo exponen).

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

## Pantallas (implementadas)
- **Constantes del sistema** (menú "Configuración"): lista con **pills por grupo con conteo**
  (endpoint `/conteos`) y banner descriptivo del grupo activo; badge **"Solo lectura"** para
  operadores; búsqueda por clave/descripción/grupo; CRUD manual del Admin (grupo/clave son
  identidad natural: no se editan) y **diálogo de importación CSV** (previsualizar → confirmar,
  reporte legible con motivos de rechazo).
- **Cuentas contables** (menú "Soporte"): catálogo simple lista + detalle + formulario, con
  `tipo_cuenta` como select. Sin carga CSV.

## Pendientes / dudas (estado)
- ✅ **Modelado de CuentaContable:** resuelto — tabla propia (ADR-024).
- ✅ **Detalle de carga masiva CSV:** resuelto e implementado (ADR-025).
- ⏳ **CuentaContable, campos extra:** pendiente confirmar con contabilidad si requieren campos
  adicionales (naturaleza, agrupador…). Hoy se implementan los 3 de la spec; si hicieran falta,
  se amplía sin romper lo existente (decisión F-6 del plan).
- ⏳ **Carga inicial de catálogos SAT:** manual por ahora; la carga masiva CSV se usará cuando
  exista la lista oficial del SAT (sin seed automático, confirmado por el equipo).