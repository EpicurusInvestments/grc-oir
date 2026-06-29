---
name: backend-fastapi
description: >
  Convenciones para implementar la lógica de backend del Sistema GRC-OIR con Python,
  FastAPI, Pydantic y SQLAlchemy sobre SQL Server (AWS RDS). Úsala SIEMPRE que se vaya
  a escribir o modificar código de backend: endpoints, servicios, repositorios, modelos,
  schemas, validaciones, máquinas de estado, campos calculados, RBAC, permisos por campo
  o auditoría de parámetros sensibles. Asegura el respeto a las capas
  (router → service → repository) y a la especificación de BD v2.
---

# Skill: backend-fastapi

Cómo implementar un módulo de backend respetando las capas y la spec BD v2.

## Arquitectura por capas (no romperla)

```
router.py  →  service.py  →  repository.py  →  SQL Server (AWS RDS)
(API/HTTP)    (negocio)       (datos)
```

- **router**: HTTP ↔ negocio. Valida permisos, usa schemas Pydantic, delega TODO al
  servicio. Cero lógica, cero SQL.
- **service**: reglas de negocio, **fórmulas calculadas**, **máquina de estados**,
  permisos por campo, auditoría, transacciones. No conoce HTTP.
- **repository**: único punto que toca la BD.

## La especificación BD v2 manda

- Nombres de entidades, campos (snake_case en español), tipos y valores de estado son
  los de la spec. No se renombran ni se "mejoran". Duda → preguntar al equipo.
- **Campos por origen** (concepto de la spec):
  - *Manual* → entrada del usuario, validada en el schema.
  - *Calculado* → SOLO el servicio lo escribe, con la fórmula de la spec
    (`iva = subtotal * IVA_RATE`, `importe_oir = importe_estacion *
    porcentaje_participacion_oir / 100`, etc.). Nunca aceptarlo en el request.
  - *Derivado/Heredado* → se copia de la entidad origen (p.ej. OrdenEstacion hereda de
    OrdenCliente) y puede ajustarse según la spec.
  - *Cat/Manual* → sugerido del catálogo con override manual; al hacer override,
    sugerir el alta del valor en el catálogo.
- Constantes de negocio (IVA_RATE=0.16, etc.) viven en configuración central, no
  repetidas en el código.

## Máquina de estados (patrón obligatorio)

Cada campo de estado tiene su `StrEnum` (en `enums.py`) y un mapa de transiciones en el
servicio. Transición no listada → error de dominio (HTTP 409 desde el router).

```python
class EstatusOrden(StrEnum):
    RECIBIDA = "recibida"; CAPTURADA = "capturada"; EN_TRANSMISION = "en_transmision"
    EN_VERIFICACION = "en_verificacion"; ORDEN_CERRADA = "orden_cerrada"
    FACTURADA = "facturada"; COBRADA = "cobrada"; CANCELADA = "cancelada"

TRANSICIONES = {
    EstatusOrden.RECIBIDA: {EstatusOrden.CAPTURADA, EstatusOrden.CANCELADA},
    # ... completar según la spec; ante duda, confirmar con el equipo
}
```

Reglas de cierre importantes de la spec (respetarlas tal cual):
- `OrdenCliente` pasa a `orden_cerrada` SOLO cuando todas sus `OrdenEstacion` están
  `reconciliada = TRUE`. `orden_cerrada` es lo único que habilita facturar.
- `OrdenEstacion` en estatus `cerrada` es lo único que Facturación puede "jalar".
- `FacturaCliente.estado_facturacion = timbrada` solo al registrar el folio fiscal
  recibido del timbrador externo.

## Endpoint con permiso (patrón)

```python
@router.post("", response_model=OrdenClienteRead, status_code=201,
             dependencies=[Depends(requiere_permiso("ordenes:capturar"))])
async def capturar_orden(data: OrdenClienteCreate,
                         service: OrdenService = Depends(get_orden_service)):
    return await service.capturar(data)
```

- El área del usuario (ventas │ facturacion │ tesoreria │ cxc │ cxp │ direccion │
  nominas │ admin) se resuelve del token de SSO; nunca del cliente.
- La matriz área × módulo (C/L/—) de la propuesta vive como configuración en
  `app/core/security.py`, no como ifs repartidos.

## Permisos por campo + auditoría de parámetros sensibles

Antes de modificar un campo sensible (p.ej. `porcentaje_comision_agencia_default`):

```python
# en el servicio:
await field_permissions.verificar(entidad="Agencia",
                                  campo="porcentaje_comision_agencia_default",
                                  usuario=usuario)          # 403 si no autorizado
await audit.log_cambio_parametro(entidad="Agencia", entidad_id=agencia_id,
                                 campo="porcentaje_comision_agencia_default",
                                 anterior=valor_actual, nuevo=valor_nuevo,
                                 usuario=usuario, ip=ip)     # → LogCambioParametro
```

Estos hooks viven en `app/core/` y se usan desde la Entrega 1, aunque la administración
de `PermisoCampo` llegue en la Fase 5.

## SQL Server / RDS (notas)

- PKs `UNIQUEIDENTIFIER`; textos `Unicode/NVARCHAR`; dinero `DECIMAL(14,2)`; estados
  `VARCHAR` + CHECK constraint. Sesión/engine central en `app/core/db.py`.
- Elegir sync (pyodbc + `def`) o async (aioodbc + `async def`) y ser consistente en
  todo el backend.
- Cambios de esquema SOLO por Alembic (skill `migraciones-sqlserver`).

## Cargas de archivo e integraciones

Endpoints de upload (NOI, movimientos bancarios, XML/PDF de facturas) validan tipo y
tamaño y delegan a `app/integrations/` (skill `integraciones-externas`). Procesos
pesados no bloquean el request.

## Calidad y cierre

- Tipos + `mypy`; lint; pruebas de casos felices, validaciones y TRANSICIONES de estado.
- Actualizar `docs/API-CONTRACT.md` y la ficha del módulo (skill `documentacion-proyecto`).
- Pasar `revision-modulo` antes del PR.
