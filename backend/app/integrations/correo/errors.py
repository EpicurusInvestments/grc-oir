"""Errores de dominio del envío de correo (ADR-105)."""

from __future__ import annotations

from app.core.errors import DomainError


class CorreoError(DomainError):
    """El backend de correo (p.ej. SES) no está disponible, mal configurado, o falló al
    enviar.

    Se mapea a 502: es una dependencia externa, no un error del cliente. El mensaje es
    legible; el detalle técnico se registra en logs, no se filtra al cliente.
    """

    codigo = "correo_no_disponible"
    status_code = 502
