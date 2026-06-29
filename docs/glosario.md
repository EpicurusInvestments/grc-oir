# Glosario — Sistema GRC-OIR

> Términos del dominio, ya sembrado desde la propuesta y la especificación BD v2.
> Documento VIVO: agregar términos nuevos conforme aparezcan en el desarrollo.

## Actores

- **Anunciante** — Cliente comercial que contrata transmisiones. Puede ser representado
  por una agencia o tratar directo. En la operación se le llama "Anunciante".
- **Agencia** — Agencia de medios que representa anunciantes ante el grupo. Cobra una
  comisión. No accede al sistema.
- **Afiliado** — Empresa externa que opera estaciones (emisoras). Factura al grupo por
  los servicios de transmisión. No accede al sistema.
- **EmpresaFacturadora** — Entidad legal del grupo que emite facturas; puede haber varias.
- **Vendedor** — Ejecutivo comercial con lógica de comisiones (principal y secundario).
- **Áreas internas** — Ventas, Facturación, Tesorería, CxC, CxP, Dirección/Finanzas,
  Nóminas, Admin (IT). Únicos usuarios del sistema.

## Operación

- **OrdenCliente (OC)** — Orden de transmisión recibida del anunciante o su agencia.
  Documento de referencia para facturación y cobro. Tiene TRES estados independientes:
  `estatus_orden`, `estatus_pago_afiliado`, `estatus_pago_agencia`.
- **OrdenEstacion (OE)** — Orden interna derivada de la OC (1 → N): una asignación a una
  estación en un horario. "Asignar" = programar con todos los datos operativos.
- **Verificación** — Registro de lo realmente transmitido según reporte del afiliado;
  se compara contra lo asignado. (En el diagrama: "horarios reales y testigos".)
- **Testigos** — Evidencias de transmisión que respaldan la verificación.
- **Incidencia** — Diferencia entre lo solicitado y lo verificado (faltante, excedente,
  cambio_horario, cambio_fecha, spot_no_emitido) con su resolución.
- **Reconciliada** — Marca de una OE validada contra lo solicitado; cuando todas las OE
  de una OC están reconciliadas, la OC puede cerrarse (`orden_cerrada`).
- **Plaza** — Plaza geográfica de transmisión; se infiere al elegir estación.
- **TarifaPlaza** — Tarifa de referencia por plaza, tipo de señal (fm/am/tv) y duración
  de spot (20s/30s/60s/mención). Valor sugerido al capturar órdenes.

## Fiscal y finanzas

- **CFDI** — Comprobante Fiscal Digital por Internet (factura electrónica mexicana).
- **Timbrado / folio fiscal** — Sellado del CFDI realizado por el proveedor EXTERNO de
  timbrado. El sistema PREPARA la factura, exporta archivo plano y RECIBE el folio.
- **Archivo plano de timbrado** — Archivo de intercambio con el timbrador (referencia:
  archivo_plano_FACTURA_33_NPG_D_28_11757_V40.txt).
- **FacturaCliente** — Carátula de la factura al cliente que el sistema prepara.
- **FacturaAfiliado / FacturaAgencia** — Facturas RECIBIDAS (captura o carga). La del
  afiliado puede distribuir su costo entre varias OE (FacturaAfiliadoOrden, N:M).
- **Requisición** — Solicitud de pago (pago_afiliado, pago_agencia, comision_vendedor,
  comision_agencia) que requiere autorización e incluye referencia a la OC de SAP.
- **OC de SAP** — Orden de compra en SAP del grupo; se captura como referencia.
- **Conciliación bancaria** — Cruce de MovimientoBancario contra pagos esperados.
- **NOI** — Formato de nómina cuyo archivo mensual alimenta CostoAdicional (tipo nomina).
- **Overhead** — Costos indirectos capturados como CostoAdicional (tipo overhead).
- **PeriodoResultados** — Consolidado mensual de ingresos y costos (Estado de Resultados
  del área): utilidad bruta y neta calculadas por fórmula.
- **Antigüedad de saldos** — Clasificación de cuentas por cobrar por días vencidos
  (corriente, 1-30, 31-60, 61-90, 90+).

## Sistema

- **Parámetro sensible** — Campo cuyo cambio requiere permiso por campo y queda
  registrado en LogCambioParametro (p.ej. porcentajes de comisión).
- **PermisoCampo** — Configuración de qué áreas/roles pueden editar campos protegidos.
- **Tags de campo** — Etiquetas de UI que indican el origen del dato: Catálogo,
  Heredado, Calculado, Derivado, Audit log, Timbrado.
- **Cat/Manual** — Origen de campo: se sugiere del catálogo pero permite captura manual.
