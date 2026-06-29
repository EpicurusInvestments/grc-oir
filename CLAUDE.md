# CLAUDE.md — Sistema GRC-OIR (Grupo Radio Centro)

> Este archivo es la **fuente de verdad** que Claude Code lee automáticamente al iniciar
> en este repositorio. Define qué es el proyecto, cómo se trabaja y qué reglas son
> inquebrantables. Si algo cambia en el proyecto, se actualiza aquí primero.
>
> Cómo leerlo: las líneas `[[POR LLENAR: ...]]` son datos que el equipo debe completar;
> mientras no estén, Claude Code **pregunta** en lugar de asumir. Hay `CLAUDE.md`
> adicionales en `backend/` y `frontend/` con reglas locales de cada capa.

## 1. Resumen del proyecto

**Sistema GRC-OIR**: plataforma web a la medida para Operaciones, Ventas y Finanzas del
área OIR de **Grupo Radio Centro**, desarrollada por **Pointwise**. Cubre el ciclo
completo: captura de órdenes de transmisión del anunciante/agencia, derivación a
estaciones afiliadas (1 → N), verificación e incidencias, preparación de facturación
(timbrado externo), cobranza, pagos vía requisiciones, conciliación bancaria y reportes
financieros con cierre mensual.

- **Cliente:** Grupo Radio Centro (área OIR).
- **Documentos rectores:** la propuesta comercial Pointwise y la **especificación de base
  de datos v2 (33 entidades, 6 fases)**. Ante cualquier duda de campos, estados o reglas,
  esos documentos mandan (copias en `docs/referencias/` — `[[POR LLENAR: colocarlos ahí]]`).
- **Responsable técnico:** `[[POR LLENAR: nombre y contacto]]`
- **Repositorio:** https://github.com/EpicurusInvestments/grc-oir.git

### Principios de diseño del sistema (vienen de la propuesta; no se negocian)

1. **Multi-estación nativo:** una `OrdenCliente` se deriva en N `OrdenEstacion`,
   preservando siempre la trazabilidad OC → OE.
2. **Trazabilidad punta a punta:** orden → factura → cobro; orden → factura de afiliado
   → requisición → pago.
3. **Catálogos como fuente única**, con sugerencia automática y opción de captura manual
   cuando un valor no existe (origen "Cat/Manual").
4. **Separación de responsabilidades por área:** cada área tiene sus pantallas y permisos
   (Ventas, Facturación, Tesorería, CxC, CxP, Dirección/Finanzas, Nóminas, Admin).
5. **Preparación, NO timbrado:** el sistema **no emite CFDI**. Prepara emisor, receptor,
   conceptos, totales y layout; exporta archivo plano al timbrador externo y **recibe**
   el folio fiscal y datos de timbrado.
6. **Auditoría sobre campos sensibles:** cambios a parámetros marcados como sensibles
   (p.ej. % de comisión) se registran en `LogCambioParametro` (usuario, fecha, valor
   anterior, valor nuevo) y se controlan con permisos **a nivel de campo** (`PermisoCampo`).
7. **Los actores externos NO acceden al sistema:** clientes, agencias y afiliados entran
   solo como datos (captura interna o carga de archivo). No hay portal externo.

## 2. Reglas de oro (cumplimiento obligatorio)

1. **Desarrollo incremental por fases/módulos.** Se trabaja una fase —y dentro de ella,
   una entidad/pantalla— a la vez, siguiendo el plan de entregas (sección 5). Nunca
   generar "toda la app" ni varias fases en paralelo sin petición explícita.
2. **Planear antes de programar.** Ante cualquier tarea, proponer un plan corto (archivos
   a crear/tocar y por qué) y esperar aprobación antes de escribir código de negocio.
3. **El modelo de datos v2 es la referencia.** Entidades, campos, tipos, estados y
   fórmulas calculadas se implementan como dice la especificación. Si algo parece
   incorrecto o ambiguo, se pregunta al equipo; no se "mejora" por cuenta propia.
4. **Respetar la arquitectura por capas.** Presentación → API → Negocio → Integración →
   Datos. Lógica de negocio fuera de routers y componentes React.
5. **Integraciones solo por la capa de integración** (`backend/app/integrations/`):
   timbrador fiscal (archivo plano), NOI de nóminas, estados de cuenta bancarios,
   facturas de proveedor (XML/PDF). SAP es **referencia capturada** (número de OC), no
   integración directa, salvo que el alcance cambie.
6. **Seguridad y auditoría no son opcionales.** RBAC por área en cada endpoint, permisos
   a nivel de campo sobre parámetros sensibles, y registro en bitácora.
7. **Documentación a la par del código.** Cada avance actualiza la documentación viva en
   `docs/` (ver sección 10 y skill `documentacion-proyecto`). Un cambio sin su
   documentación actualizada NO está terminado.
8. **Cambios pequeños y revisables.** Commits y PRs chicos, enfocados a una fase/entidad.
9. **Cuando dudes, pregunta.** Datos `[[POR LLENAR]]`, alcance ambiguo o decisiones con
   consecuencias → preguntar, no asumir.

## 3. Stack tecnológico (decidido)

| Capa | Tecnología | Notas |
|---|---|---|
| Frontend | **React + TypeScript** | **Vite** (SPA; el sistema es interno autenticado, no necesita SSR). TS estricto. |
| Librería UI | **PrimeReact** | Elegida por su DataTable potente (filtros, paginación, selección) y componentes densos, que calzan con el patrón lista + panel de detalle de las pantallas aprobadas. |
| Backend | **Python + FastAPI** | Pydantic v2, SQLAlchemy 2.x, Alembic. |
| Base de datos | **Microsoft SQL Server en AWS RDS** | Endpoint y accesos vía variables de entorno (`.env`), nunca en el código. Driver: **pyodbc (síncrono)** + ODBC Driver 18. (Síncrono por simplicidad y madurez con SQL Server; FastAPI corre los endpoints `def` en threadpool.) |
| Entorno local | **Docker / Docker Desktop** | Backend y frontend corren en contenedores (`docker-compose.yml` en la raíz). BD de desarrollo: instancia RDS `devapps...` (ver decisión pendiente sobre separar dev/prod). |
| Identidad | SSO corporativo `[[POR LLENAR: Azure AD / Google Workspace / otro — por confirmar con IT de GRC]]` | RBAC por área + permisos por campo. |
| Tipografía UI | IBM Plex Sans (texto) / IBM Plex Mono (folios, claves) | Definido en la propuesta, sección 7. |
| Runtimes | Python **3.12** · Node **20 LTS** | Versiones fijadas en los Dockerfiles. |

## 4. Estructura del repositorio

```
grc-oir/
├── CLAUDE.md                  # este archivo (reglas globales)
├── docker-compose.yml         # backend + frontend en contenedores locales
├── .env.example               # variables de entorno de referencia (sin secretos reales)
├── .claude/skills/            # skills del proyecto (sección 9)
├── backend/
│   ├── CLAUDE.md              # reglas del backend
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py
│   │   ├── core/              # config, seguridad, RBAC, permisos por campo, auditoría, BD
│   │   ├── modules/           # un subpaquete por módulo de negocio (ver regla de espejo)
│   │   ├── integrations/      # timbrador, noi, bancos, facturas proveedor (anti-corrupción)
│   │   └── shared/
│   ├── migrations/            # Alembic
│   └── pyproject.toml
├── frontend/
│   ├── CLAUDE.md              # reglas del frontend
│   ├── Dockerfile
│   └── src/
│       ├── app/               # router, layout (header/sidebar), providers
│       ├── modules/           # espeja backend/app/modules
│       └── shared/            # ui, lib, hooks comunes (tabla, panel detalle, tags)
└── docs/                      # DOCUMENTACIÓN VIVA (se actualiza con cada avance)
    ├── arquitectura.md        # decisiones de arquitectura y diagramas
    ├── API-CONTRACT.md        # contrato de la API: endpoints, validaciones, ejemplos
    ├── GITHUB_WORKFLOW.md     # ramas, commits, PRs
    ├── glosario.md            # términos del dominio
    ├── modulos/               # un .md por módulo: alcance, estados, pantallas, reglas
    └── referencias/           # propuesta, especificación BD v2, ERD, diagrama de flujo
```

**Regla de espejo:** cada módulo existe con el mismo nombre en
`backend/app/modules/<modulo>/` y `frontend/src/modules/<modulo>/`.

### Mapa fases → módulos de código

Las **fases** (F0–F5) son unidades de alcance/entrega; los **módulos** son unidades de
código. Correspondencia inicial (ajustable con el equipo):

| Fase | Módulos de código sugeridos | Entidades (33 en total) |
|---|---|---|
| **F0 Catálogos** | `catalogos` (o uno por grupo: `comerciales`, `operativos`, `financieros`), `usuarios` | Agencia, Anunciante, Contrato, Marca, EmpresaFacturadora, Vendedor, Plaza, Afiliado, Estacion, TarifaPlaza, MetodoPago, CuentaContable, LayoutFactura, Categoria, Usuario |
| **F1 Órdenes** | `ordenes` | OrdenCliente, OrdenEstacion, Verificacion, Incidencia |
| **F2 Facturación** | `facturacion`, `costos` | FacturaCliente, FacturaAfiliado, FacturaAfiliadoOrden, FacturaAgencia, CostoAdicional |
| **F3 Cobranza y Pagos** | `cobranza`, `pagos` | CobranzaFactura, PagoCliente, Requisicion, MovimientoBancario |
| **F4 Reportes** | `reportes` | PeriodoResultados |
| **F5 Seguridad** | `seguridad` (mucho vive en `core/`) | LogCambioParametro, PermisoCampo |

## 5. Plan de entregas y flujo de trabajo

Entregas incrementales según la propuesta (cada una usable en producción):

| Entrega | Fases | Resultado |
|---|---|---|
| **Entrega 1** | F0 + F1 | OIR opera el día a día: catálogos + órdenes con verificación y cierre. |
| **Entrega 2** | F2 | Ciclo comercial: preparación de facturas, folio externo, facturas Af/Ag, costos. |
| **Entrega 3** | F3 | Ciclo financiero: cobranza, requisiciones, conciliación bancaria. |
| **Entrega 4** | F4 + F5 | Reportería ejecutiva + seguridad/auditoría completa. |

> Nota: aunque las entidades de F5 se entregan al final, los **mecanismos** transversales
> (columnas de auditoría, registro en bitácora, hooks de permisos por campo) se
> construyen en `core/` desde la Entrega 1 para no re-trabajar después.

### Flujo para desarrollar cada módulo/entidad

1. Ficha de alcance en `docs/modulos/<modulo>.md` (basada en la especificación BD v2).
2. Modelo de datos + migración (skill `migraciones-sqlserver`).
3. Backend: repository → service → schemas → router (skill `backend-fastapi`).
4. Pruebas del backend.
5. Frontend: types → api → hooks → components → pages (skill `frontend-react`).
6. **Actualizar documentación** (skill `documentacion-proyecto`).
7. Revisión final (skill `revision-modulo`) → PR pequeño.

## 6. Modelo de datos: convenciones obligatorias (de la especificación v2)

- **PKs:** UUID (`UNIQUEIDENTIFIER` en SQL Server), autogeneradas. Nombre `<entidad>_id`.
- **Nombres:** snake_case en español, tal como la especificación
  (`nombre_agencia`, `porcentaje_comision_agencia_default`, etc.). No traducir ni "mejorar".
- **Timestamps:** `created_at NOT NULL`, `updated_at` en toda entidad; donde la spec lo
  indique, también `created_by`/usuario.
- **Estados como dimensiones independientes.** Ejemplos clave (valores exactos de la spec):
  - `OrdenCliente.estatus_orden`: recibida → capturada → en_transmision → en_verificacion
    → **orden_cerrada** (habilita facturación) → facturada → cobrada │ cancelada.
    Además `estatus_pago_afiliado` y `estatus_pago_agencia` (pendiente │ en_revision │ pagado).
  - `OrdenEstacion.estatus`: borrador → asignada → en_transmision → en_revision →
    **cerrada** (solo entonces Facturación puede jalar) │ cancelada.
  - `FacturaCliente.estado_facturacion`: preparada → enviada_a_timbrado → timbrada →
    entregada → cobrada │ cancelada.
  - `CobranzaFactura.estatus_cobro`: pendiente │ cobro_parcial │ cobrada │ vencida.
  - `Requisicion.estatus_requisicion`: pendiente → autorizada → pagada │ cancelada.
- **ENUMs:** SQL Server no tiene tipo ENUM; se implementan como `VARCHAR` + `CHECK
  constraint` (o tabla catálogo si el equipo lo decide). Los valores son los de la spec.
- **Campos calculados:** la spec define fórmulas (p.ej. `iva = subtotal * 0.16`,
  `importe_oir = importe_estacion * porcentaje_participacion_oir / 100`). Se calculan en
  la capa de **servicio** (no en el front, no a mano) y se persisten según la spec.
  La tasa de IVA y similares se centralizan en configuración, no se repiten en el código.
- **Parámetros sensibles:** campos marcados "PARÁMETRO SENSIBLE" (p.ej.
  `porcentaje_comision_*`) requieren: permiso por campo (`PermisoCampo`) + registro
  automático en `LogCambioParametro` al cambiar.
- **Transiciones de estado:** validar transiciones permitidas en el servicio (máquina de
  estados explícita). P.ej. una `OrdenCliente` pasa a `orden_cerrada` solo cuando todas
  sus `OrdenEstacion` están `reconciliada = TRUE`.

## 7. Seguridad

- SSO corporativo (por confirmar) + sesión de usuario interno con **área**:
  ventas │ facturacion │ tesoreria │ cxc │ cxp │ direccion │ nominas │ admin.
- **RBAC por área** según la matriz de la propuesta (sección 9): C = captura, L = lectura,
  — = sin acceso. Implementarla como datos/configuración, no hardcodeada por pantalla.
- **Permisos a nivel de campo** sobre parámetros sensibles (F5, pero el hook se construye
  desde el inicio en `core/`).
- HTTPS/TLS, OWASP Top 10, validación de toda entrada.
- Bitácora `LogCambioParametro` para campos sensibles + auditoría general de operaciones.
- Nunca loguear datos personales/fiscales innecesarios; secretos solo en variables de
  entorno o gestor de secretos (**AWS Secrets Manager** recomendado para QA/producción; en local, `.env`).

## 8. Integraciones (capa anti-corrupción en `backend/app/integrations/`)

| Integración | Dirección | Mecanismo |
|---|---|---|
| **Timbrador fiscal externo** | Salida/Entrada | Exporta archivo plano por factura (estructura de referencia: `archivo_plano_FACTURA_33_NPG_D_28_11757_V40.txt` — `[[POR LLENAR: conseguir spec del formato]]`). Recibe folio fiscal + datos de timbrado → `FacturaCliente`. **El sistema NO timbra.** |
| **SAP** | Referencia | Las requisiciones capturan el número de OC de SAP como referencia. Sin integración directa (alcance ampliado a evaluar). |
| **NOI de nóminas** | Entrada | Carga de archivo mensual; parseo y validación → `CostoAdicional` tipo `nomina`. `[[POR LLENAR: spec del formato NOI]]` |
| **Estados de cuenta bancarios** | Entrada | Carga manual o archivo → `MovimientoBancario` para conciliación. `[[POR LLENAR: banco(s) y formato]]` |
| **Facturas de proveedor (Af/Ag)** | Entrada | Captura manual o carga XML/PDF; validación de RFC contra catálogo. |
| **Exportación a Excel** | Salida | Todos los reportes y listas exportables a Excel/CSV. |

Detalle de implementación en la skill `integraciones-externas`.

## 9. Skills del proyecto (`.claude/skills/`)

- **`nuevo-modulo`** — andamiaje de un módulo (back + front) sin lógica de negocio.
- **`backend-fastapi`** — capas, Pydantic, RBAC, permisos por campo, auditoría, SQL Server.
- **`frontend-react`** — patrón de pantallas de la propuesta (lista + panel detalle, forms full-screen, tags).
- **`migraciones-sqlserver`** — Alembic contra AWS RDS SQL Server (UUID, CHECK, NVARCHAR).
- **`integraciones-externas`** — adaptadores: timbrador, NOI, bancos, facturas proveedor.
- **`documentacion-proyecto`** — mantiene `docs/` al día con cada cambio (obligatoria al cerrar tareas).
- **`revision-modulo`** — Definición de Terminado antes de cada PR.

## 10. Documentación viva (obligatoria, a la par del código)

Política: **el código y su documentación viajan en el mismo PR.** La skill
`documentacion-proyecto` define qué actualizar según el tipo de cambio. Documentos:

- `docs/arquitectura.md` — decisiones de arquitectura (formato ADR ligero) y diagramas.
- `docs/API-CONTRACT.md` — contrato de la API: endpoints, payloads, validaciones,
  ejemplos. Se complementa con el OpenAPI generado por FastAPI (la fuente técnica), pero
  este documento agrega contexto de negocio, reglas y ejemplos legibles para el equipo.
- `docs/GITHUB_WORKFLOW.md` — ramas, commits, PRs, revisiones.
- `docs/glosario.md` — términos del dominio (ya sembrado).
- `docs/modulos/<modulo>.md` — alcance, entidades, estados, pantallas y reglas por módulo.
- `docs/referencias/` — documentos fuente (propuesta, spec BD v2, ERD, diagrama de flujo).

## 11. Entorno local con Docker

- `docker-compose.yml` levanta **backend** y **frontend** en contenedores con hot-reload
  (volúmenes montados). La BD es la instancia **AWS RDS SQL Server** (no hay contenedor
  de BD por defecto; hay uno opcional comentado para trabajar sin conexión).
- Credenciales/endpoint de RDS en `.env` (copiar de `.env.example`). **Nunca** commitear `.env`.
- El backend necesita el **ODBC Driver 18 for SQL Server** dentro de la imagen (ya
  contemplado en `backend/Dockerfile`).
- Comandos:
```bash
docker compose up --build        # levantar todo
docker compose exec backend bash # entrar al contenedor del backend
docker compose exec backend alembic upgrade head   # migraciones contra RDS
docker compose exec backend pytest        # pruebas backend
docker compose exec backend ruff check .  # lint backend
docker compose exec frontend npm run lint # lint frontend
```

## 12. Git y flujo de trabajo

Definido en `docs/GITHUB_WORKFLOW.md`. Resumen: `main` protegida, ramas
`feature/f<fase>-<modulo>-<tarea>`, Conventional Commits en español
(`feat(ordenes): ...`), un PR por tarea con su documentación actualizada.
`[[POR LLENAR: nº de revisores y reglas de protección de ramas]]`

## 13. Lo que NO debe hacer Claude Code (guardarraíles)

- ❌ Desarrollar varias fases/módulos a la vez o "toda la app".
- ❌ Programar lógica de negocio sin presentar un plan corto y recibir aprobación.
- ❌ Cambiar nombres de entidades/campos o valores de estados respecto a la spec BD v2.
- ❌ Implementar timbrado de CFDI: el sistema solo **prepara** y **recibe** el folio.
- ❌ Crear integración directa con SAP (es referencia capturada) sin nuevo alcance aprobado.
- ❌ Crear endpoints sin RBAC, o editar parámetros sensibles sin permiso por campo + bitácora.
- ❌ Modificar el esquema fuera de una migración Alembic.
- ❌ Poner credenciales (RDS, timbrador, etc.) en código o en archivos versionados.
- ❌ Cerrar una tarea sin actualizar la documentación correspondiente en `docs/`.
- ❌ Crear pantallas o portales para actores externos (clientes/agencias/afiliados).
- ❌ Inventar datos `[[POR LLENAR]]`: preguntar.

## 14. Decisiones pendientes (resolver con el equipo)

- **"MODIFICAR FLUJO PAGO DE AGENCIA"** (nota roja del diagrama actualizado): el flujo de
  pago a agencias está marcado para cambio. `[[POR LLENAR: nuevo flujo acordado]]`
- Cómo acumulan las agencias sus facturas (nota del diagrama: "al parecer incluyen más
  cosas"). `[[POR LLENAR]]`
- Envío de la factura al cliente: ¿correo automático del sistema, descarga por ventas, o
  correo al vendedor? `[[POR LLENAR]]`
- SSO definitivo (Azure AD / Google Workspace / otro). `[[POR LLENAR]]`
- Formato exacto del archivo plano del timbrador y del NOI. `[[POR LLENAR]]`
- ¿BD de desarrollo separada de producción en RDS? Recomendado SÍ. Hoy se usa la
  instancia/BD de pruebas `devapps.../GRC-OIR`; definir cuándo y cómo se crea la de
  producción. `[[POR LLENAR: decisión y endpoint de prod]]`

## 15. Glosario rápido

Glosario completo en `docs/glosario.md`. Mínimos: **OrdenCliente (OC)** orden recibida
del anunciante/agencia; **OrdenEstacion (OE)** orden interna derivada por estación;
**Verificación/Testigos** registro de lo realmente transmitido; **Incidencia** diferencia
entre lo solicitado y lo verificado; **Timbrado/folio fiscal** sellado del CFDI por el
proveedor externo; **Requisición** solicitud de pago autorizable (afiliado, agencia,
comisiones) con referencia a OC de SAP; **NOI** formato de nómina que alimenta costos.
