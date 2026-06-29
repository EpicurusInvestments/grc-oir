# CLAUDE.md — Backend (Python / FastAPI / SQL Server en AWS RDS)

> Reglas locales del backend. Hereda y no contradice el `CLAUDE.md` raíz.
> La referencia de entidades, campos, estados y fórmulas es la **especificación BD v2**.

## Stack

- **FastAPI** + **Pydantic v2** + **SQLAlchemy 2.x** + **Alembic**.
- SQL Server en **AWS RDS**. Driver: **pyodbc (síncrono)**
  sobre **ODBC Driver 18 for SQL Server** (instalado en el Dockerfile).
  <!-- ¿Por qué importa? El driver define si los endpoints son `def` (sync) o `async def`.
       Elegir UNO y ser consistente en todo el backend; mezclar provoca bloqueos sutiles. -->
- Conexión SOLO vía variables de entorno (ver `.env.example`):
  `DB_HOST` (endpoint RDS), `DB_PORT=1433`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  más `TrustServerCertificate`/`Encrypt` según la configuración TLS de la instancia.
- Gestor de dependencias: **uv** (rápido y reproducible con lockfile).

## Capas dentro de cada módulo (obligatorio)

```
modules/<modulo>/
├── router.py       # Capa API: endpoints, validación de permisos. SIN lógica de negocio.
├── service.py      # Capa Negocio: reglas, fórmulas calculadas, máquina de estados, transacciones.
├── repository.py   # Capa Datos: ÚNICO lugar que consulta/escribe la BD.
├── models.py       # Entidades SQLAlchemy (tablas según la spec v2).
├── schemas.py      # DTOs Pydantic de entrada y salida.
└── tests/
```

El `router` llama al `service`; el `service` al `repository`. Nunca al revés ni
saltándose capas. Nunca devolver entidades SQLAlchemy crudas: siempre schemas `XxxRead`.

## Convenciones del modelo de datos (de la spec v2 — NO cambiarlas)

- **PKs UUID** → en SQL Server: `UNIQUEIDENTIFIER` con default generado.
  En SQLAlchemy: `Uuid` / `UNIQUEIDENTIFIER` del dialecto mssql. Nombre: `<entidad>_id`.
- **Nombres snake_case en español** exactamente como la spec
  (`porcentaje_comision_agencia_default`, `estatus_pago_afiliado`...).
- **Textos**: usar `NVARCHAR` (en SQLAlchemy, `Unicode(n)`) para soportar acentos/ñ.
  <!-- VARCHAR en SQL Server no es UTF-8 por defecto; con NVARCHAR evitamos corrupción
       de caracteres en razones sociales y nombres. -->
- **Montos**: `DECIMAL(14,2)` (o lo que diga la spec por campo). Nunca float para dinero.
- **ENUMs**: SQL Server no tiene ENUM → `VARCHAR` + **CHECK constraint** con los valores
  exactos de la spec. En Python, un `enum.StrEnum` por estado, fuente única de verdad.
- **Estados independientes**: una entidad puede tener varios estados a la vez
  (p.ej. `OrdenCliente`: `estatus_orden`, `estatus_pago_afiliado`, `estatus_pago_agencia`).
  No combinarlos en un solo campo.
- **Máquina de estados en el servicio**: las transiciones válidas se validan en
  `service.py` (p.ej. `orden_cerrada` solo si todas las `OrdenEstacion` están
  `reconciliada = TRUE`). Transición inválida → error de dominio claro.
- **Campos calculados**: implementar las fórmulas de la spec en el servicio y persistir.
  <!-- Ejemplos de la spec: iva = subtotal * 0.16; importe_oir = importe_estacion *
       porcentaje_participacion_oir / 100; importe_pendiente_cobro = total_factura -
       importe_cobrado. La tasa de IVA vive en configuración central, no repetida. -->
  Los campos de origen "Calculado" NUNCA se aceptan como entrada del cliente.
- **Origen "Cat/Manual"**: el campo se sugiere desde catálogo pero permite captura manual;
  al capturarse manual, el sistema sugiere incorporar el valor al catálogo.

## Seguridad (RBAC + permisos por campo)

- Cada endpoint declara su permiso: `dependencies=[Depends(requiere_permiso("ordenes:capturar"))]`.
  El área del usuario (ventas │ facturacion │ tesoreria │ cxc │ cxp │ direccion │
  nominas │ admin) se resuelve del token de SSO, nunca del cliente.
- La **matriz área × módulo** de la propuesta se implementa como configuración en
  `app/core/security.py` (datos, no ifs repartidos por el código).
- **Permisos a nivel de campo** (`PermisoCampo`): antes de modificar un campo marcado
  como sensible, el servicio verifica el permiso vía `app/core/field_permissions.py`.
  <!-- Este hook se construye desde la Entrega 1 aunque la entidad PermisoCampo se
       administre en F5: así no hay que re-trabajar los servicios después. -->

## Auditoría

- Cambios a campos con `requiere_audit_log = TRUE` generan registro en
  `LogCambioParametro`: entidad, entidad_id, campo, valor anterior, valor nuevo,
  usuario, fecha, ip. Implementado una sola vez en `app/core/audit.py` y llamado desde
  los servicios (o vía listener de SQLAlchemy si el equipo lo aprueba).

## API

- Todo bajo `/api/v1`, documentado en OpenAPI (no desactivar `/docs`).
- Esquema de errores uniforme (handler central en `app/core/errors.py`).
- Cargas de archivo (NOI, layouts bancarios, XML de facturas) → endpoints de upload que
  delegan a la capa de integración; validar tamaño/tipo antes de procesar.
- Procesos pesados o con terceros NO bloquean el request:
  **FastAPI BackgroundTasks** para empezar (timbrado, parseos); migrar a una cola (Celery/RQ) si el volumen lo exige. Decisión revisable al llegar a F2.

## Docker (entorno local)

- El backend corre en contenedor (ver `backend/Dockerfile` y `docker-compose.yml`).
- Hot-reload con volumen montado: editar local, el contenedor recarga.
- Migraciones se ejecutan DENTRO del contenedor (`docker compose exec backend alembic ...`)
  para usar el mismo driver ODBC que producción.

## Calidad

- Tipos en todo + `mypy`. Lint/format **ruff**. Pruebas con `pytest`
  (mínimo: casos felices, validaciones de dominio y transiciones de estado).
- No crear dependencias directas entre módulos; lo compartido va a `app/shared/`.
