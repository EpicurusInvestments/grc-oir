# Módulo F0-05 — Constantes del sistema (catálogos SAT / timbrador) · Fase: F0

> Pantalla "Constantes del sistema": catálogos del SAT y configuración del timbrador
> externo que **consume Facturación (F2)**. Solo lectura para los operadores; edición
> restringida al administrador. Referencia: `Fase_0_-_Catalogos.html` (grupo "constantes").

## Propósito

Centralizar los valores fiscales válidos que el sistema usará al **preparar** las
facturas para el timbrador externo (recordar: el sistema NO timbra). Son los valores
que el operador podrá elegir en las pantallas de facturación (F2).

## Entidad / modelo

Una entidad de configuración tipo "constante" con: `id` (PK), `grupo` (a qué catálogo
SAT pertenece), `clave` (el valor SAT), `descripcion`, `valor` (opcional, p.ej. legacy
"33"), `activo`, `updated_at`.

### Grupos (de la pantalla)
- **TipoComprobante** — Tipo de comprobante CFDI (I, E, P; "33" legacy del timbrador).
- **Serie** — Serie de la factura.
- **RegimenFiscal** — Régimen fiscal SAT.
- **ClaveProdServ** — Clave de producto/servicio SAT.
- **ClaveUnidad** — Clave de unidad SAT.
- **UsoCFDI** — Uso del CFDI.
- **FormaPago** — Forma de pago SAT.
- **MetodoPago** — Método de pago SAT.
- **MonedaSAT** — Moneda.

## Estados
- Solo `activo`. Filtrado por grupo y búsqueda por clave/descripción/grupo.

## Pantallas (de la pantalla F0)
- Lista con **filtros por grupo** (pills con conteo por grupo) y badge **"Solo lectura"**
  en el encabezado. Para el operador es consulta; el alta/edición es solo del Admin.
- Subtítulo de la pantalla: indica que estos valores alimentan las pantallas de
  Facturación (4.1/4.2 en la numeración interna).

## Roles / permisos
- Lectura: todas las áreas operativas. Edición: Admin (IT) únicamente.

## Reglas de negocio clave
- Estos catálogos NO se editan en operación normal; cambian poco y de forma controlada.
- Los valores deben corresponder a los catálogos oficiales del SAT vigentes (CFDI 4.0).
  `[[POR LLENAR: confirmar de dónde se obtiene/actualiza la lista oficial del SAT]]`

## Integraciones
- Indirecta: estos valores se usan al **preparar el archivo plano** para el timbrador
  externo (módulo de F2). No hay llamada a servicios aquí.

## Dependencias
- F0-00 (fundamentos). Conviene tenerlo listo antes de iniciar F2.

## Pendientes / dudas
- Mecanismo de carga inicial: ¿seed con los catálogos SAT o carga manual por Admin?
  `[[POR LLENAR]]`
- ¿Quién y con qué frecuencia actualiza estos catálogos cuando el SAT cambia? `[[POR LLENAR]]`
