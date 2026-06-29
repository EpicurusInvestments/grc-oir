---
name: integraciones-externas
description: >
  Cómo construir los puntos de integración del Sistema GRC-OIR: timbrador fiscal externo
  (archivo plano de factura y recepción de folio fiscal), archivos NOI de nóminas,
  estados de cuenta bancarios para conciliación, carga de facturas de proveedor (XML/PDF
  de afiliados y agencias) y exportaciones a Excel. Úsala SIEMPRE que se intercambien
  datos con sistemas o archivos externos, o cuando aparezcan palabras como timbrado,
  CFDI, folio fiscal, archivo plano, NOI, layout bancario, conciliación, XML de factura
  o SAP. Garantiza el patrón anti-corrupción: nada externo se filtra al dominio.
---

# Skill: integraciones-externas

Todas las integraciones viven en `backend/app/integrations/` y exponen una interfaz
limpia en términos del dominio (patrón anti-corrupción). El resto de la app nunca
conoce formatos de archivos externos.

## Principio clave del proyecto

**El sistema NO timbra CFDI.** Prepara la información de la factura, exporta un archivo
plano al timbrador externo y RECIBE el folio fiscal + datos de timbrado. Cualquier
solicitud de "integrar un PAC" o timbrar directo contradice la propuesta → detenerse y
consultar al equipo.

**SAP es referencia capturada**: las requisiciones guardan el número de OC de SAP como
texto de referencia. NO construir consultas/escrituras directas a SAP salvo nuevo
alcance aprobado (decisión registrada como ADR-003 en `docs/arquitectura.md`).

## Estructura de un adaptador

```
backend/app/integrations/<sistema>/
├── port.py         # interfaz en términos del dominio; el negocio depende SOLO de esto
├── adapter.py      # implementación del port
├── mapper.py       # traducción formato externo ↔ modelo del dominio
└── parser.py / writer.py   # lectura/escritura del formato de archivo (si aplica)
```

El servicio de negocio recibe el `port` por inyección → se simula en pruebas y se
reemplaza sin tocar el dominio.

## Por integración

### Timbrador fiscal (salida/entrada)
- **Salida**: `port.exportar_factura(factura) -> archivo` genera el archivo plano con
  la estructura acordada (referencia: `archivo_plano_FACTURA_33_NPG_D_28_11757_V40.txt`;
  spec exacta `[[POR LLENAR: conseguir formato y reglas]]`). Estado de la factura:
  `preparada → enviada_a_timbrado`.
- **Entrada**: registro del folio fiscal y datos de timbrado → `timbrada`.
  Validar que la factura esté `enviada_a_timbrado` antes de aceptar el folio.
- Idempotencia: re-exportar no debe duplicar; registrar cada exportación para trazabilidad.

### NOI de nóminas (entrada)
- Carga del archivo mensual; `parser.py` valida estructura y rechaza archivos
  malformados con error claro (qué línea/columna falló).
- Resultado: registros `CostoAdicional` tipo `nomina` con su período.
- Formato exacto: `[[POR LLENAR: spec del NOI usado por GRC]]`.

### Estados de cuenta bancarios (entrada)
- Carga manual o por archivo → `MovimientoBancario` (cargo │ abono) para conciliación.
- Validar duplicados (mismo banco, fecha, referencia, monto) antes de insertar.
- Banco(s) y formato(s): `[[POR LLENAR]]`.

### Facturas de proveedor — afiliados y agencias (entrada)
- Captura manual o carga de XML/PDF. Si es XML de CFDI: extraer RFC, folio, montos y
  **validar el RFC contra el catálogo** (Afiliado/Agencia) antes de aceptar.
- FacturaAfiliado se distribuye entre OrdenEstacion vía `FacturaAfiliadoOrden` (N:M);
  la suma distribuida debe cuadrar con el monto de la factura.

### Exportación a Excel/CSV (salida)
- Utilidad compartida (`app/shared/`) usada por todas las listas y reportes; respeta
  los filtros activos de la vista.

## Reglas generales

- Nunca llamar/parsear formatos externos desde un router o un componente React.
- Archivos grandes y procesos de conciliación NO bloquean el request
  (`[[POR LLENAR: BackgroundTasks/cola]]`), con resultado consultable.
- Errores externos → mapear a errores del dominio claros (el usuario debe entender
  qué archivo/registro falló y por qué).
- Auditar cargas y exportaciones (quién, cuándo, qué archivo, resultado).
- Credenciales/rutas en configuración; nada en el código.
- Probar `parser`/`mapper` con ejemplos reales **anonimizados**; probar servicios con
  dobles del `port`.
