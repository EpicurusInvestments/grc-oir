---
name: migraciones-sqlserver
description: >
  Cómo crear, revisar y aplicar migraciones de base de datos del Sistema GRC-OIR con
  Alembic sobre Microsoft SQL Server en AWS RDS. Úsala SIEMPRE que se vaya a cambiar el
  esquema: crear o alterar tablas, columnas, índices, llaves foráneas, CHECK constraints
  de estados, o al implementar entidades de la especificación BD v2. El esquema NUNCA se
  cambia a mano en la base: siempre por migración.
---

# Skill: migraciones-sqlserver

Toda modificación del esquema pasa por Alembic contra la instancia AWS RDS. Nada de
cambios manuales en SQL Server Management Studio / Azure Data Studio.

## Flujo

1. Ajustar/crear el modelo SQLAlchemy en `backend/app/modules/<modulo>/models.py`,
   siguiendo la **especificación BD v2** (nombres, tipos y restricciones exactos).
2. Generar migración DENTRO del contenedor (mismo driver ODBC que producción):
   ```bash
   docker compose exec backend alembic revision --autogenerate -m "crear tabla agencia"
   ```
3. **Revisar SIEMPRE** el archivo generado en `backend/migrations/versions/`:
   la autogeneración de Alembic no detecta bien renombres ni algunos ALTER en SQL
   Server. Confirmar tipos, nulabilidad, FKs, índices, CHECKs y que el `downgrade`
   revierta correctamente.
4. Aplicar en desarrollo:
   ```bash
   docker compose exec backend alembic upgrade head
   ```
5. Verificar que la app levanta y las pruebas pasan.

## Convenciones de esquema (de la spec v2 + SQL Server)

- **PK**: `UNIQUEIDENTIFIER` con default (`NEWID()`/generación en app — decidir y ser
  consistentes: `[[POR LLENAR]]`). Nombre `<entidad>_id`.
- **Textos**: `NVARCHAR(n)` (en SQLAlchemy `Unicode(n)`) — soporta acentos/ñ sin
  corromper. Longitudes según la spec (p.ej. nombre_agencia NVARCHAR(200), RFC 13).
- **Dinero**: `DECIMAL(14,2)` (o lo que indique la spec por campo). Nunca FLOAT.
- **Booleanos**: `BIT`. **Fechas**: `DATE` / `DATETIME2`.
- **Estados (ENUM de la spec)**: columna `VARCHAR` + **CHECK constraint** con los
  valores exactos, p.ej.:
  ```sql
  CONSTRAINT ck_ordencliente_estatus_orden CHECK (estatus_orden IN
    ('recibida','capturada','en_transmision','en_verificacion',
     'orden_cerrada','facturada','cobrada','cancelada'))
  ```
  Dar nombre explícito a cada constraint (facilita futuras migraciones).
- **FKs explícitas** con comportamiento ON DELETE/UPDATE pensado (evitar cascadas
  accidentales en datos financieros; preferir RESTRICT/NO ACTION salvo acuerdo).
- **Índices**: en FKs y columnas de búsqueda/filtrado frecuentes (folios, RFC, fechas,
  estatus de bandejas).
- **Timestamps**: `created_at NOT NULL` (+ `updated_at`, `created_by` donde la spec lo pida).
- **Relación N:M**: tabla puente con su propia PK cuando la spec lo defina así
  (p.ej. `FacturaAfiliadoOrden`).

## AWS RDS (notas)

- Conexión vía variables del `.env` (endpoint, puerto 1433, credenciales); TLS según la
  instancia (`Encrypt`/`TrustServerCertificate`).
- RDS no da acceso de sistema operativo: todo se hace por conexión SQL estándar
  (Alembic funciona normal).
- Recomendado tener BD de desarrollo separada de la futura productiva
  (`[[POR LLENAR: estrategia de ambientes en RDS]]`). Las migraciones a QA/producción
  las controla el flujo de despliegue del equipo, no se corren "a mano" desde local.
- Antes de migraciones destructivas en ambientes compartidos: snapshot de RDS.

## Datos iniciales (seeds)

- Catálogos con valores predefinidos (MetodoPago SAT, áreas, etc.): migraciones de
  datos separadas y claramente nombradas, o mecanismo de seed aparte:
  `[[POR LLENAR: estrategia de seeds]]`.
- Nunca incluir secretos ni datos personales reales en migraciones.

## Reglas

- Una migración por cambio lógico, mensaje descriptivo en español.
- La migración y la ficha del módulo (`docs/modulos/`) se actualizan en el mismo PR.
