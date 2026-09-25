"""Puerto de envío de correo (patrón anti-corrupción, ADR-105, mismo criterio que
`AlmacenamientoPort`/ADR-020).

El dominio (servicios de negocio) depende SOLO de esta interfaz; el adaptador concreto
(SES real o el local que solo registra en el log) se inyecta por configuración.
"""

from __future__ import annotations

from typing import Protocol

# Adjunto: (nombre_archivo, contenido, content_type).
Adjunto = tuple[str, bytes, str]


class CorreoPort(Protocol):
    """Envío de correo en términos del dominio."""

    def enviar(
        self,
        *,
        destinatario: str | list[str],
        asunto: str,
        cuerpo_texto: str,
        adjuntos: list[Adjunto] | None = None,
    ) -> None:
        """Envía un correo (con adjuntos opcionales) a uno o varios destinatarios."""
        ...
