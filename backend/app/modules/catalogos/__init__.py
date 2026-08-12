"""Módulo `catalogos`.

Cada catálogo (plaza, afiliado, ...) es un submódulo/archivo que define su modelo +
schemas + (opcional) subclase de servicio, y se cuelga del router agregador con una sola
llamada a `build_crud_router`.

La base reutilizable (`BaseRepository`, `BaseService`, `build_crud_router`, `schemas`)
vive en `app.shared` (reubicada desde aquí en ADR-032): la usan todos los módulos, no
solo `catalogos`, así que no le corresponde vivir dentro de un módulo hermano.
"""
