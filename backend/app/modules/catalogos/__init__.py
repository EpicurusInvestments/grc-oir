"""Módulo `catalogos`.

F0-00 deja aquí la BASE REUTILIZABLE de todos los catálogos (sin entidad propia):
- `base_repository.BaseRepository` — acceso a datos genérico con filtros + paginación.
- `base_service.BaseService` — reglas comunes y conversión a schema de salida.
- `crud_router.build_crud_router` — factory de endpoints CRUD con RBAC ya cableado.
- `schemas` — `Page[T]`, `ListParams`, `CambioEstadoIn`, `CatalogoReadBase`.

Desde F0-01, cada catálogo (plaza, afiliado, ...) será un submódulo/archivo que define
su modelo + schemas + (opcional) subclase de servicio, y se cuelga del router agregador
con una sola llamada a `build_crud_router`.
"""
