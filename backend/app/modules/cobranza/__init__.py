"""Módulo `cobranza` (F3 — Cobranza y Pagos).

Las 4 entidades de la spec BD v2 (sección "FASE 3") se implementan JUNTAS por su
acoplamiento — mismo criterio que F0/F1/F2 —, en dos archivos según su dominio de
negocio real:

- `cobranza_factura.py` — `CobranzaFactura` + `PagoCliente` (CxC: cobro de facturas
  al cliente que F2 ya timbró).
- `requisicion.py`      — `Requisicion` (CxP: pago a afiliados/agencias/comisiones,
  con autorización de Dirección).
- `movimiento_bancario.py` — `MovimientoBancario` (Tesorería: conciliación manual).
- `adjuntos.py`         — comprobantes de pago (`PagoCliente`) y archivos de estado
  de cuenta (`MovimientoBancario`), con la factory compartida (ADR-067). `Requisicion`
  no tiene campo de archivo propio en la spec: sus facturas de proveedor ya se adjuntan
  por `facturacion/adjuntos.py` (F2), a través de `factura_afiliado_id`/
  `factura_agencia_id`.

Dos desviaciones ADITIVAS aprobadas, ambas ya usadas por F2 con el mismo criterio:

1. `metodo_pago_id` (FK a `MetodoPago`) → `metodo_pago_clave`, texto SIN FK formal:
   `MetodoPago` vive dentro de `ConstantesSistema` (grupo `MetodoPago`, F0-05).
2. `estatus_cobro` almacena solo 3 valores (`pendiente`/`cobro_parcial`/`cobrada`);
   `vencida` es un badge DERIVADO en el servicio, nunca una columna — ver el docstring
   de `cobranza_factura.py`.

RBAC: DOS claves de módulo (`cobranza`, `pagos`), predefinidas por el mapa de módulos
del `CLAUDE.md` §4 — mismo patrón que F2 (ADR-044):

- `cobranza` — WRITE: CxC (`CobranzaFactura`, `PagoCliente`).
- `pagos`    — WRITE: CxP (`Requisicion`). `MovimientoBancario` es un caso especial
  DENTRO de esta misma clave: Tesorería captura y CxP no, así que el router usa
  `pagos:leer` (nivel de módulo, el más bajo que ambas áreas comparten) y el chequeo
  real de `Area.TESORERIA` vive dentro del servicio — mismo canal dedicado del
  ADR-046 que ya usa la autorización de Dirección en `Requisicion`/F2.

El handoff con F2 (creación automática de `CobranzaFactura` al timbrar, su cancelación
al cancelar la factura, y la cascada de cobro hacia `FacturaCliente`/`OrdenCliente`) se
documenta en el docstring de `cobranza_factura.py` — es el corazón de este módulo.
"""
