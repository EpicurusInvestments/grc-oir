# Módulo F0-04 — Catálogos de facturación/finanzas y base de Usuario · Fase: F0

> Catálogos de apoyo a Facturación y Finanzas, en su mayoría CRUD simple, más el
> **modelo** mínimo de Usuario para el RBAC (su pantalla de administración vive en F5).
> Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupos "vendedor", "categoria").
>
> **Alcance ajustado (respuestas del equipo, ver "Decisiones confirmadas"):** de las 7
> entidades originalmente contempladas, este módulo implementa **solo 4**: EmpresaFacturadora,
> Vendedor, Categoria y el modelo de Usuario. MetodoPago y CuentaContable se gestionan en
> `ConstantesSistema` (F0-05); LayoutFactura se omite por ahora.

## Propósito

Completar los catálogos que F2 (Facturación) y F4 (Reportes) necesitan: empresa
facturadora, vendedores (con comisión) y categorías comerciales. Dejar listo el modelo de
Usuario/área para el control de acceso.

## Entidades a implementar en F0-04

### EmpresaFacturadora (6 campos)
`empresa_facturadora_id` (PK), `nombre_empresa` (NOT NULL), `rfc_empresa` (NOT NULL),
`direccion_empresa`, `activo`, `created_at`. (El grupo puede tener varias razones sociales.)
- **Pantalla:** catálogo simple, ubicado en el menú **"Soporte"** del sidebar.

### Vendedor (6 campos)
`vendedor_id` (PK), `nombre_vendedor` (NOT NULL), `email_vendedor`,
**`porcentaje_comision_default` (DECIMAL · PARÁMETRO SENSIBLE — tag «Audit log»)**,
`activo`, `created_at`. Separado de Usuario porque tiene lógica de comisiones.
- **Pantalla:** grupo propio en el sidebar (menú "Soporte"), lista + detalle.

### Categoria (5 campos)
`categoria_id` (PK), `nombre_categoria` (NOT NULL), `descripcion_categoria`, `activo`,
`created_at`. (Automotriz, Alimentos, Telecom, etc.)
- **Pantalla:** grupo propio en el sidebar (menú "Soporte"), lista + detalle.

### Usuario (7 campos) — solo el MODELO aquí
`usuario_id` (PK), `nombre_usuario` (NOT NULL), `email` (NOT NULL), `area` (ENUM:
ventas│facturacion│tesoreria│cxc│cxp│direccion│nominas│admin), `roles_adicionales`,
`activo`, `created_at`.
- En F0 se construye el modelo + seed mínimo para arrancar el RBAC. La **pantalla**
  "Usuarios y áreas" pertenece al módulo de F5.

## Entidades EXCLUIDAS de F0-04 (decisiones del equipo)

- **MetodoPago:** NO se crea tabla ni pantalla propia. Su captura y manejo se agrupan en
  la pantalla "Constantes del sistema" (menú "Configuración"), guardándose en la entidad
  `ConstantesSistema`. Corresponde a **F0-05**.
- **CuentaContable:** igual que MetodoPago — se gestiona en `ConstantesSistema` (F0-05).
  Sin tabla ni pantalla propia.
- **LayoutFactura:** se **omite por ahora** (ni entidad, ni pantalla). Si el negocio lo
  requiere más adelante, se reintroduce como tarea aparte. Registrar como desviación en
  `docs/arquitectura.md` (ADR).

## Estados
- Todos por `activo` (baja lógica). Sin máquina de estados.

## Pantallas (de la pantalla F0)
- **Vendedor** y **Categoria**: grupo propio en el sidebar, bajo el menú **"Soporte"**
  (lista + detalle, filtros Activos/Inactivos/Todos, paginación por página).
- **EmpresaFacturadora**: catálogo simple, también bajo el menú **"Soporte"**.
- Botones `+ Nuevo vendedor`, `+ Nueva categoría`, `+ Nueva empresa facturadora`.

## Roles / permisos (matriz RBAC)
- **Captura/edición: solo Admin (IT)** por ahora (consistente con F0-01..F0-03). El
  tratamiento completo de permisos por área se aborda en la fase de seguridad (F5).
- Lectura: demás áreas.
- `porcentaje_comision_default` (Vendedor): **parámetro sensible** con permiso por campo
  (`field_permissions.verificar`) + registro en `LogCambioParametro` (mismo mecanismo de
  F0-03). Por ahora solo Admin puede modificarlo; en F5 se abrirá a Dirección si aplica.

## Reglas de negocio clave
- RFC de EmpresaFacturadora válido (persona moral); puede haber varias empresas facturadoras.
- `porcentaje_comision_default` del vendedor: parámetro sensible (mismo tratamiento que
  F0-03 — auditoría en alta con `anterior=None` y en edición cuando cambia, motivo requerido).
- `nombre_categoria` recomendable único (confirmar); Categoria es catálogo simple.
- **Vendedor principal/secundario y sus comisiones NO se modelan aquí:** se modelan en la
  **orden** (F1). En F0-04, Vendedor es solo el catálogo con su comisión default.

## Auditoría
- Un campo sensible en este módulo: `Vendedor.porcentaje_comision_default`. Reutiliza el
  mecanismo `audit.registrar_cambio_sensible` / `LogCambioParametro` ya construido en F0-03.
  El panel de detalle de Vendedor debe mostrar su "Historial de cambios" (reutilizando
  `BaseService.historial`, como en F0-03).

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos) y los hooks de permiso por campo + auditoría de `core/` (ya en uso
  desde F0-03).

## Decisiones confirmadas (respuestas del equipo)
1. **MetodoPago y CuentaContable** → se agrupan en `ConstantesSistema` (F0-05); sin tabla
   ni pantalla propia en F0-04.
2. **LayoutFactura** → omitido por ahora (registrar desviación en ADR).
3. **EmpresaFacturadora** → catálogo simple, pantalla bajo el menú "Soporte".
4. **RBAC** → solo Admin (IT) captura/edita; permisos por área se afinan en F5.
5. **Vendedor principal/secundario** → se modela en la orden (F1), no aquí.

## Estado de implementación
- **Tanda 1 (backend + migración): IMPLEMENTADA.** Migración `f1a4d0c25e63`
  (`empresa_facturadora`, `vendedor`, `categoria`, `usuario` + seed admin). Reutiliza el
  mecanismo de auditoría de F0-03 para el % de Vendedor (cero código nuevo en `core/`);
  ruta `GET /catalogos/vendedores/{id}/historial`. Decisiones registradas en ADR-022
  (omisiones) y ADR-023 (Usuario + seed).
- **Tanda 2 (frontend):** pendiente.
- **Tanda 3 (cierre + revision-modulo):** pendiente.

## Decisiones menores (resueltas)
- `nombre_categoria` **único, case-insensitive** (E-1). `rfc_empresa` **único** (E-2).
  `email` de Usuario **único** (E-3). `roles_adicionales` texto libre NVARCHAR (E-5).
- `updated_at` en los 3 catálogos (ADR-011); Usuario con sus 7 campos exactos (E-6).
- **Seed de Usuario:** un admin alineado al dev — `nombre_usuario='dev.admin'`,
  `email='dev.admin@grcoir.com'`, `area='admin'` (E-4). Sin usuarios por área (eso es F5).
- `direccion_empresa` como **TEXT** (NVARCHAR(MAX)), fiel a la spec (pág. 9).
