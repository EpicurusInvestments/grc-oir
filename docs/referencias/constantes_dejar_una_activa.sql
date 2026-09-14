/* =============================================================================
   Deja UNA sola constante activa por grupo fiscal — atajo para cerrar el archivo
   plano del PAC (ADR-048).
   Motor: Microsoft SQL Server.

   POR QUÉ EXISTE
   --------------
   `FacturaClienteService._constante_unica()` usa la constante de un grupo SOLO si hay
   exactamente una activa. Con varias, elegir cuál es una decisión fiscal que nadie ha
   tomado y adivinarla produciría un CFDI que timbra pero está mal; por eso el campo se
   reporta como faltante. Este script toma esa decisión de forma explícita.

   VALORES ELEGIDOS
   ----------------
   No son inventados: son los que trae el archivo plano REAL de producción
   (`docs/referencias/ejemplo_archivo_plano_FACTURA_33_NPG_D_28_11757_V40 (2).txt`),
   del que se reconstruyó el layout V40 (ADR-048).

     RegimenFiscal   601        General de Ley Personas Morales
     UsoCFDI         G03        Gastos en general
     ClaveProdServ   82101601   Spots o servicios de transmisión publicitaria
     ClaveUnidad     E48        Unidad de servicio
     FormaPago       99         Por definir

   QUÉ **NO** TOCA (a propósito)
   -----------------------------
   - `MetodoPago`: el usuario ELIGE PUE o PPD en el formulario de factura. Dejar una sola
     activa vaciaría media opción del combo. No lo lee `_constante_unica`.
   - `Serie`: `IdDoc.Serie` se deriva del prefijo del número de factura ("A-1041" → "A"),
     no del catálogo (ADR-060 bis).
   - `TipoComprobante` y `MonedaSAT`: no los lee `_constante_unica` hoy.

   ES UN ATAJO, NO LA SOLUCIÓN
   ---------------------------
   Funciona mientras haya UNA emisora y todos los receptores compartan régimen. Con una
   segunda `EmpresaFacturadora` o un cliente persona física deja de servir: el régimen
   pertenece a cada entidad (`EmpresaFacturadora`/`Anunciante`/`Agencia`) y el UsoCFDI al
   cliente. Ese es el diseño correcto pendiente de aprobación.

   REVERSIBLE: solo cambia `activo`. Para volver atrás, se reactivan desde la pantalla de
   Catálogos (queda auditado) o con el UPDATE comentado al final.
   ============================================================================= */

SET NOCOUNT ON;

BEGIN TRANSACTION;

DECLARE @ahora DATETIME2 = SYSUTCDATETIME();

/* Grupo -> clave que se conserva activa. */
DECLARE @elegidas TABLE (
    grupo NVARCHAR(40)  NOT NULL,
    clave NVARCHAR(100) NOT NULL
);

INSERT INTO @elegidas (grupo, clave) VALUES
 (N'RegimenFiscal', N'601'),
 (N'UsoCFDI',       N'G03'),
 (N'ClaveProdServ', N'82101601'),
 (N'ClaveUnidad',   N'E48'),
 (N'FormaPago',     N'99');

/* Aviso si alguna de las elegidas no existe: sin ella el grupo quedaría con CERO activas
   y el campo seguiría reportándose como faltante. Corre antes el seed del catálogo. */
IF EXISTS (
    SELECT 1 FROM @elegidas AS e
    WHERE NOT EXISTS (
        SELECT 1 FROM constantes_sistema AS c
        WHERE c.grupo = e.grupo AND c.clave = e.clave
    )
)
BEGIN
    SELECT N'FALTA en el catálogo' AS aviso, e.grupo, e.clave
    FROM @elegidas AS e
    WHERE NOT EXISTS (
        SELECT 1 FROM constantes_sistema AS c
        WHERE c.grupo = e.grupo AND c.clave = e.clave
    );
    ROLLBACK TRANSACTION;
    RAISERROR (N'Alguna constante elegida no existe. Corre antes seed_constantes_sistema.sql.', 16, 1);
    RETURN;
END;

/* 1) Desactiva las demás del grupo. */
UPDATE c
   SET c.activo = 0,
       c.updated_at = @ahora
  FROM constantes_sistema AS c
  JOIN @elegidas AS e ON e.grupo = c.grupo
 WHERE c.clave <> e.clave
   AND c.activo = 1;

PRINT CONCAT(N'Constantes desactivadas: ', @@ROWCOUNT);

/* 2) Asegura que la elegida quede activa (por si estaba dada de baja). */
UPDATE c
   SET c.activo = 1,
       c.updated_at = @ahora
  FROM constantes_sistema AS c
  JOIN @elegidas AS e ON e.grupo = c.grupo AND e.clave = c.clave
 WHERE c.activo = 0;

PRINT CONCAT(N'Constantes reactivadas: ', @@ROWCOUNT);

COMMIT TRANSACTION;

/* Verificación: los 5 grupos fiscales deben quedar en 1; MetodoPago intacto en 2. */
SELECT grupo, COUNT(*) AS activas
FROM constantes_sistema
WHERE activo = 1
GROUP BY grupo
ORDER BY grupo;


/* -----------------------------------------------------------------------------
   PARA REVERTIR (reactiva todo el catálogo de esos 5 grupos):

   UPDATE constantes_sistema
      SET activo = 1, updated_at = SYSUTCDATETIME()
    WHERE grupo IN (N'RegimenFiscal', N'UsoCFDI', N'ClaveProdServ',
                    N'ClaveUnidad', N'FormaPago')
      AND activo = 0;
   ----------------------------------------------------------------------------- */
