/* =============================================================================
   Carga del catálogo `constantes_sistema` (F0-05)
   Origen: prototipo aprobado docs/referencias/pantallas/Fase_0_-_Catalogos.html
   31 registros en 9 grupos SAT/timbrador.

   Motor: Microsoft SQL Server.

   IDEMPOTENTE: cada INSERT valida que no exista ya el par (grupo, clave), que es la
   identidad natural del registro. Se puede correr varias veces sin duplicar ni fallar.
   La comparación usa la colación de la columna, que es CI (case-insensitive), igual que
   la validación del servicio.

   NO actualiza los registros que ya existan: si una descripción cambió, se edita desde
   la pantalla de Catálogos para que quede auditado.
   ============================================================================= */

SET NOCOUNT ON;

BEGIN TRANSACTION;

DECLARE @ahora DATETIME2 = SYSUTCDATETIME();

/* Tabla temporal con los valores del prototipo. Se carga primero y se inserta con un
   solo NOT EXISTS: más legible que 31 IF separados, y una sola pasada sobre la tabla. */
DECLARE @nuevas TABLE (
    grupo       NVARCHAR(40)  NOT NULL,
    clave       NVARCHAR(100) NOT NULL,
    descripcion NVARCHAR(400) NOT NULL,
    valor       NVARCHAR(200) NULL
);

INSERT INTO @nuevas (grupo, clave, descripcion, valor) VALUES
-- ── TipoComprobante (CFDI 4.0 — campo 'Tipo' del archivo plano) ──
 (N'TipoComprobante', N'I',  N'Ingreso · facturas, notas de cargo',                        NULL),
 (N'TipoComprobante', N'E',  N'Egreso · notas de crédito',                                 NULL),
 (N'TipoComprobante', N'P',  N'Pago · complementos de pago',                               NULL),
 (N'TipoComprobante', N'33', N'Factura tradicional (legacy del timbrador externo)',        N'33'),

-- ── Serie del CFDI ──
 (N'Serie', N'D', N'Serie D — Radio Publicidad XHMéxico (División OIR)', N'D'),
 (N'Serie', N'A', N'Serie A — Grupo Radio Centro Servicios',             N'A'),

-- ── RegimenFiscal ──
 (N'RegimenFiscal', N'601', N'General de Ley Personas Morales',                                  NULL),
 (N'RegimenFiscal', N'603', N'Personas Morales con Fines no Lucrativos',                         NULL),
 (N'RegimenFiscal', N'612', N'Personas Físicas con Actividades Empresariales y Profesionales',   NULL),
 (N'RegimenFiscal', N'626', N'Régimen Simplificado de Confianza',                                NULL),

-- ── ClaveProdServ (catálogo SAT — los usados típicamente por radio) ──
 (N'ClaveProdServ', N'82101501', N'Servicios de publicidad por radio',              NULL),
 (N'ClaveProdServ', N'82101601', N'Spots o servicios de transmisión publicitaria',  NULL),
 (N'ClaveProdServ', N'82101599', N'Otros servicios de publicidad',                  NULL),
 (N'ClaveProdServ', N'80141600', N'Servicios de mercadeo / patrocinios',            NULL),

-- ── ClaveUnidad ──
 (N'ClaveUnidad', N'E48', N'Unidad de servicio', NULL),
 (N'ClaveUnidad', N'ACT', N'Actividad',          NULL),
 (N'ClaveUnidad', N'H87', N'Pieza',              NULL),

-- ── UsoCFDI ──
 (N'UsoCFDI', N'G01',  N'Adquisición de mercancías', NULL),
 (N'UsoCFDI', N'G03',  N'Gastos en general',         NULL),
 (N'UsoCFDI', N'P01',  N'Por definir',               NULL),
 (N'UsoCFDI', N'S01',  N'Sin efectos fiscales',      NULL),
 (N'UsoCFDI', N'CP01', N'Pagos',                     NULL),

-- ── FormaPago ──
 (N'FormaPago', N'01', N'Efectivo',                            NULL),
 (N'FormaPago', N'02', N'Cheque nominativo',                   NULL),
 (N'FormaPago', N'03', N'Transferencia electrónica de fondos', NULL),
 (N'FormaPago', N'04', N'Tarjeta de crédito',                  NULL),
 (N'FormaPago', N'28', N'Tarjeta de débito',                   NULL),
 (N'FormaPago', N'99', N'Por definir',                         NULL),

-- ── MetodoPago ──
 (N'MetodoPago', N'PUE', N'Pago en una sola exhibición',      NULL),
 (N'MetodoPago', N'PPD', N'Pago en parcialidades o diferido', NULL),

-- ── MonedaSAT ──
 (N'MonedaSAT', N'MXN', N'Peso mexicano',          NULL),
 (N'MonedaSAT', N'USD', N'Dólar estadounidense',   NULL),
 (N'MonedaSAT', N'EUR', N'Euro',                   NULL);


INSERT INTO constantes_sistema
    (constante_sistema_id, grupo, clave, descripcion, valor, activo, created_at, updated_at)
SELECT
    NEWID(), n.grupo, n.clave, n.descripcion, n.valor, 1, @ahora, NULL
FROM @nuevas AS n
WHERE NOT EXISTS (
    SELECT 1
    FROM constantes_sistema AS c
    WHERE c.grupo = n.grupo
      AND c.clave = n.clave
);

PRINT CONCAT(N'Constantes insertadas: ', @@ROWCOUNT);

COMMIT TRANSACTION;

/* Verificación */
SELECT grupo, COUNT(*) AS activas
FROM constantes_sistema
WHERE activo = 1
GROUP BY grupo
ORDER BY grupo;
