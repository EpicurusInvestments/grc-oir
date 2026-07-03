# Módulo F0-04 — Catálogos de facturación/finanzas y base de Usuario · Fase: F0

> Catálogos de apoyo a Facturación y Finanzas, en su mayoría CRUD simple, más el
> **modelo** mínimo de Usuario para el RBAC (su pantalla de administración vive en F5).
> Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupos "vendedor", "categoria").

## Propósito

Completar los catálogos que F2 (Facturación) y F4 (Reportes) necesitan: empresa
facturadora, vendedores (con comisión), categorías comerciales, y los catálogos
contables/fiscales internos. Dejar listo el modelo de Usuario/área para el control de
acceso.

## Entidades (spec BD v2)

### EmpresaFacturadora (6 campos)
`empresa_facturadora_id` (PK), `nombre_empresa` (NOT NULL), `rfc_empresa` (NOT NULL),
`direccion_empresa`, `activo`, `created_at`. (El grupo puede tener varias razones sociales.)

### Vendedor (6 campos)
`vendedor_id` (PK), `nombre_vendedor` (NOT NULL), `email_vendedor`,
**`porcentaje_comision_default` (DECIMAL · PARÁMETRO SENSIBLE — tag «Audit log»)**,
`activo`, `created_at`. Separado de Usuario porque tiene lógica de comisiones.

### Categoria (5 campos)
`categoria_id` (PK), `nombre_categoria` (NOT NULL), `descripcion_categoria`, `activo`,
`created_at`. (Automotriz, Alimentos, Telecom, etc.)

### MetodoPago (4 campos)
`metodo_pago_id` (PK), `clave_metodo` (NOT NULL), `descripcion_metodo`, `activo`.
Catálogo SAT de métodos de pago.

### CuentaContable (5 campos)
`cuenta_contable_id` (PK), `codigo_cuenta` (NOT NULL), `nombre_cuenta`, `tipo_cuenta`
(ENUM: ingreso│costo│gasto│activo│pasivo), `activo`.

### LayoutFactura (5 campos)
`layout_factura_id` (PK), `nombre_layout` (NOT NULL), `descripcion_layout`,
`archivo_plantilla_path`, `activo`. Plantillas de impresión de factura por cliente/operación.

### Usuario (7 campos) — solo el MODELO aquí
`usuario_id` (PK), `nombre_usuario` (NOT NULL), `email` (NOT NULL), `area` (ENUM:
ventas│facturacion│tesoreria│cxc│cxp│direccion│nominas│admin), `roles_adicionales`,
`activo`, `created_at`.
- En F0 se construye el modelo + seed mínimo para arrancar el RBAC. La **pantalla**
  "Usuarios y áreas" pertenece al módulo de F5.

## Estados
- Todos por `activo` (lógica). Sin máquina de estados.

## Pantallas (de la pantalla F0)
- Vendedor y Categoría tienen grupo propio en el sidebar (lista + detalle, filtros
  Activos/Inactivos). Botones `+ Nuevo vendedor`, `+ Nueva categoría`.
- MetodoPago, CuentaContable, LayoutFactura, EmpresaFacturadora: pantallas de catálogo
  simple (algunas pueden mostrarse como parte de "constantes/configuración" según la
  versión final). `[[POR LLENAR: confirmar si tienen pantalla propia o se agrupan]]`

## Roles / permisos
- Captura: Admin (IT). `porcentaje_comision_default` (Vendedor): solo Dirección
  (permiso por campo + audit log). Lectura: Facturación/Finanzas. `[[POR LLENAR: confirmar]]`

## Reglas de negocio clave
- RFC de EmpresaFacturadora válido; puede haber varias empresas facturadoras.
- `porcentaje_comision_default` del vendedor: parámetro sensible (mismo tratamiento que F0-03).
- `clave_metodo` y `codigo_cuenta` únicos.

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos) y hooks de permiso/auditoría de `core/`.

## Pendientes / dudas
- ¿Cuáles de estos catálogos tienen pantalla propia y cuáles se agrupan bajo
  "configuración"? `[[POR LLENAR]]`
- Vendedor principal y secundario con comisiones (la propuesta los menciona): confirmar
  si la comisión secundaria se modela aquí o en la orden. `[[POR LLENAR]]`
