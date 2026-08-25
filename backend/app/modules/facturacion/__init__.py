"""Módulo `facturacion` (F2 — Facturación).

Las 5 entidades de la spec BD v2 (sección "FASE 2") se implementan JUNTAS por su
acoplamiento: `FacturaCliente` es el centro y las otras tres dependen de ella o de la
`OrdenCliente`. Un archivo por entidad (o entidad + su hija directa), igual que F0 y F1.

- `factura_cliente.py`  — FacturaCliente (33 campos, máquina de estados propia).
- `factura_afiliado.py` — FacturaAfiliado + FacturaAfiliadoOrden (N:M contra OrdenEstacion).
- `factura_agencia.py`  — FacturaAgencia (1:N contra OrdenCliente).
- `costo_adicional.py`  — CostoAdicional (sin máquina de estados).
- `adjuntos.py`         — subida/descarga de XML/PDF del CFDI y archivos de proveedor.

Dos desviaciones ADITIVAS aprobadas respecto a la spec, ambas por catálogos que nunca
se construyeron en F0 (ver ficha del módulo):
  1. `layout_factura_id` (FK a LayoutFactura) → `layout_factura`, texto libre NULLABLE.
  2. `metodo_pago_id` (FK a MetodoPago) → `metodo_pago_clave`, texto SIN FK formal:
     `MetodoPago` vive dentro de `ConstantesSistema` (grupo `MetodoPago`, F0-05), así
     que el frontend sugiere desde ahí pero la base no valida la relación.

RBAC: DOS claves de módulo, no una (`_nivel()` resuelve por MÓDULO, no por entidad, y la
matriz de la ficha pide áreas distintas por entidad) — `facturacion` (captura
Facturación) para FacturaCliente y `costos` (captura CxP) para las otras tres. Es el
mismo par de nombres que el mapa de módulos del CLAUDE.md §4 ya predefine para F2.
"""
