# Glosario — Sistema GRC-OIR

> Términos del dominio, ya sembrado desde la propuesta y la especificación BD v2.
> Documento VIVO: agregar términos nuevos conforme aparezcan en el desarrollo.

## Actores

- **Anunciante** — Cliente comercial que contrata transmisiones. Puede ser representado
  por una agencia o tratar directo. En la operación se le llama "Anunciante".
- **Agencia** — Agencia de medios que representa anunciantes ante el grupo. Cobra una
  comisión. No accede al sistema.
- **Marca** — Marca comercial de un anunciante (p.ej. "Pan Bimbo"). Se administra anidada
  dentro del anunciante (no tiene pantalla propia), como la estación dentro del afiliado.
- **Contrato** — Contrato comercial entre el grupo y un anunciante: define vigencia
  (`fecha_inicio`/`fecha_fin`), monto, condiciones y una **comisión específica** que
  sobreescribe el default de la agencia. Tiene su propia máquina de estados
  (`estado_contrato`: vigente → suspendido/finalizado/cancelado) independiente de `activo`.
- **Afiliado** — Empresa externa que opera estaciones (emisoras). Factura al grupo por
  los servicios de transmisión. No accede al sistema.
- **EmpresaFacturadora** — Entidad legal del grupo que emite facturas; puede haber varias
  (RFC único). `direccion_empresa` es texto largo (TEXT en la spec).
- **Vendedor** — Ejecutivo comercial. Tiene un `porcentaje_comision_default` (**parámetro
  sensible**, auditado). La comisión por vendedor principal/secundario de una orden se
  modela en la orden (F1), no en el catálogo.
- **Categoria** — Categoría de industria (Automotriz, Alimentos, Telecom…) para segmentar
  órdenes y reportes. `nombre_categoria` único (case-insensitive).
- **Usuario** — Persona interna con un `area` (ventas│facturacion│tesoreria│cxc│cxp│
  direccion│nominas│admin) para el RBAC. En F0 se crea el modelo + seed mínimo; su pantalla
  de administración es F5.
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
- **Estación** — Emisora (FM/AM/TV) operada por un afiliado. `tipo_senal ∈ {fm, am, tv}`.
  **Hereda la plaza de su afiliado** (ADR-005): no se captura, se deriva. Se administra
  anidada dentro del afiliado (no tiene pantalla propia).
- **TarifaPlaza** — Tarifa de referencia por plaza, tipo de señal (fm/am/tv) y duración
  de spot (20s/30s/60s/mención). Valor sugerido al capturar órdenes.
- **Tarifa bruta / Tarifa neta** — La bruta es el precio de lista; la **neta** es un campo
  **Calculado** por el sistema: `bruta * (1 - descuento_pct/100)`. No se captura.
- **Vigencia (de tarifa)** — Periodo `[vigencia_desde, vigencia_hasta]` en que aplica una
  tarifa. Una tarifa es **Vigente** si su fin no es anterior a hoy, o **Expirada** si ya
  venció (derivado de la fecha, no un estado guardado). Dos tarifas activas de la misma
  combinación (plaza + señal + duración) **no pueden solaparse** en vigencia.

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
- **ConstantesSistema** — Catálogos SAT/timbrador que el sistema usa al PREPARAR la factura
  para el timbrador externo (F2). Entidad de configuración homogénea (`grupo`/`clave`/
  `descripcion`/`valor`) con 9 grupos: TipoComprobante, Serie, RegimenFiscal, ClaveProdServ,
  ClaveUnidad, UsoCFDI, FormaPago, MetodoPago, MonedaSAT. Solo lectura para operadores; el
  Admin las edita (manual o por carga masiva CSV). Unicidad `(grupo, clave)` (la misma clave
  puede repetirse entre grupos).
- **MetodoPago (SAT)** — Grupo de ConstantesSistema con los métodos de pago del SAT: PUE
  (pago en una sola exhibición) o PPD (pago en parcialidades o diferido). Se difirió de F0-04
  y se gestiona como constante SAT, no como tabla propia.
- **CuentaContable** — Catálogo contable interno: `codigo_cuenta` (único), `nombre_cuenta` y
  `tipo_cuenta` (ENUM: ingreso│costo│gasto│activo│pasivo). Se modela como **tabla propia**
  (no dentro de ConstantesSistema) por tener estructura distinta a las constantes SAT.

## Importación de archivos

- **Carga masiva CSV** — Alta de muchos registros a la vez desde un archivo CSV (además de la
  captura manual). Debut en F0-05 para ConstantesSistema. El archivo se procesa en memoria y
  no se persiste en el servidor.
- **Dry-run → confirmar** — Patrón de la carga masiva: primero se sube en modo previsualización
  (`commit=false`, NO escribe) y se muestra el reporte de qué se haría; solo si el usuario
  confirma, se re-sube (`commit=true`) para aplicar. Stateless (el cliente re-sube el mismo
  archivo).
- **Modo de duplicados** — Qué hacer cuando una clave del archivo ya existe: `actualizar`
  (upsert, default e idempotente), `omitir` (conservar sin cambios) o `rechazar`.
- **Import parcial** — Las filas válidas se importan aunque otras sean inválidas; las
  rechazadas se reportan con su motivo. Las válidas se aplican de forma atómica (todo o nada).

## Autenticación y sesión (F5-00)

- **Proveedor de autenticación** — Mecanismo intercambiable con el que el sistema decide
  quién es el usuario. Se elige con `AUTH_PROVIDER` y hay uno solo activo por entorno:
  `local` (email + contraseña, el que usan las demos), `dev_headers` (solo desarrollo) y
  `azure_ad` (preparado, sin implementar). Ver ADR-028.
- **Token de sesión (JWT)** — Credencial firmada que el navegador manda en cada petición
  (`Authorization: Bearer …`). Lleva la identidad y el área, y **caduca a las 8 horas**
  (una jornada, configurable). No guarda contraseñas y el servidor no lo almacena.
- **`dev_headers`** — Modo de desarrollo que conserva los headers `X-Dev-User`/`X-Dev-Area`
  para que el equipo pruebe cualquier área sin loguearse. **Solo funciona con
  `APP_ENV=development`**; fuera de ahí el sistema rechaza (ADR-008).
- **Hash de contraseña** — Huella irreversible de la contraseña (bcrypt) que es lo ÚNICO
  que se guarda: la contraseña en claro no se persiste, no se registra en logs y no se
  devuelve nunca por la API. En la UI solo se informa `tiene_password` (sí/no).
- **Área** — Único atributo que decide los permisos de un usuario: ventas │ facturacion │
  tesoreria │ cxc │ cxp │ direccion │ nominas │ admin. Un usuario tiene exactamente una.
- **Guardarraíl anti-auto-bloqueo** — Regla que impide que alguien se desactive o se cambie
  de área a sí mismo: el último Admin podría dejar al sistema sin quien administre usuarios.
- **Log de seguridad** — Registro de acciones sensibles que no son "cambios de parámetro"
  (hoy: el reseteo de contraseña — quién, a quién, desde qué IP y cuándo, **sin** la
  contraseña ni el hash). Escribe al log de la aplicación; la bitácora formal, con tabla y
  pantalla, es de F5 pleno. Distinto de [LogCambioParametro](#sistema).

## Sistema

- **Parámetro sensible** — Campo cuyo cambio requiere permiso por campo y queda
  registrado en LogCambioParametro (p.ej. porcentajes de comisión, días de crédito). Al
  modificarlo se exige un "motivo del cambio".
- **LogCambioParametro** — Bitácora de cambios a parámetros sensibles: entidad, id, campo,
  valor anterior/nuevo, usuario, fecha, ip y motivo. Se escribe desde F0-03 (una fila por
  cambio, incluida el alta); su pantalla de administración completa llega en F5. Cada
  catálogo con campos sensibles ofrece una lectura acotada por entidad
  (`/catalogos/<recurso>/{id}/historial`).
- **PermisoCampo** — Configuración de qué áreas/roles pueden editar campos protegidos.
- **Tags de campo** — Etiquetas de UI que indican el origen del dato: Catálogo,
  Heredado, Calculado, Derivado, Audit log, Timbrado.
- **Cat/Manual** — Origen de campo: se sugiere del catálogo pero permite captura manual.
