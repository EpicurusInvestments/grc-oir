"""Módulo `ordenes` (F1 — Órdenes de Transmisión).

Entidades de la spec BD v2 (sección "FASE 1"), con las desviaciones aditivas aprobadas
y documentadas en ADR-029 (comisiones snapshot), ADR-030 (`orden_estacion_dia`, tres
capas asignado/programado/verificado, testigos/reportes), ADR-031 (Incidencia híbrida
automática/manual), ADR-033 (checklist Vo.Bo. como tabla hija) y ADR-034 (campos de
cierre). Un archivo por entidad (o grupo de entidad + su hija directa), igual que F0 —
NO la separación models/schemas/repository/service/router de la skill `nuevo-modulo`:
ese patrón no es el que F0 usa en la práctica.

- `orden_cliente.py` — OrdenCliente, OrdenClienteVoBoItem (checklist).
- `orden_estacion.py` — OrdenEstacion, OrdenEstacionDia (periodo por día).
- `verificacion.py` — Verificacion.
- `incidencia.py` — Incidencia.
"""
