"""Adaptador LOCAL del puerto de correo (ADR-105) — no envía nada real.

Default para dev/pruebas: SES en modo sandbox exige verificar cada destinatario de
antemano, así que un envío real no es viable sin acceso a la cuenta de AWS. El resto del
flujo (PDF generado, bitácora `LogEnvioCorreoOrdenEstacion`) se ejercita igual que con SES.

ADR-122 (petición del usuario): además de registrar en el log, arma el MISMO mensaje MIME
que armaría `CorreoSES` (mismo `construir_mime`) y lo guarda como archivo `.eml` en
`<STORAGE_LOCAL_ROOT>/correos_simulados/` — un correo real (asunto, cuerpo, adjuntos con
su contenido real) que se puede abrir con el cliente de correo de escritorio para revisar
cómo quedó armado, SIN mandar nada a internet ni depender de credenciales de AWS/SES.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from app.integrations.correo.mime import construir_mime
from app.integrations.correo.port import Adjunto

logger = logging.getLogger(__name__)

# Remitente de mentira: en modo local nunca se manda nada, así que no hace falta un
# SES_FROM_EMAIL real configurado — pero el .eml necesita ALGÚN valor en "From" para que
# los clientes de correo lo abran sin quejarse.
_REMITENTE_SIMULADO = "pruebas-grc-oir@simulado.local"


def _nombre_archivo_seguro(destinatario: str | list[str]) -> str:
    if isinstance(destinatario, str):
        primero = destinatario
    else:
        primero = destinatario[0] if destinatario else "sin_destinatario"
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", primero)
    return f"{datetime.now():%Y%m%d_%H%M%S}_{seguro}.eml"


class CorreoLocal:
    """Implementación local del puerto: no envía nada real — registra el intento en el
    log Y guarda el mensaje armado como `.eml` (ADR-122) para poder revisarlo."""

    def __init__(self, carpeta_salida: str | Path = "_storage_local") -> None:
        self._carpeta = Path(carpeta_salida) / "correos_simulados"

    def enviar(
        self,
        *,
        destinatario: str | list[str],
        asunto: str,
        cuerpo_texto: str,
        adjuntos: list[Adjunto] | None = None,
    ) -> None:
        mensaje = construir_mime(
            remitente=_REMITENTE_SIMULADO,
            destinatario=destinatario,
            asunto=asunto,
            cuerpo_texto=cuerpo_texto,
            adjuntos=adjuntos,
        )
        self._carpeta.mkdir(parents=True, exist_ok=True)
        ruta = self._carpeta / _nombre_archivo_seguro(destinatario)
        ruta.write_bytes(mensaje.as_bytes())

        logger.info(
            "correo_local destinatario=%s asunto=%s adjuntos=%s archivo=%s",
            destinatario,
            asunto,
            [nombre for nombre, _contenido, _tipo in (adjuntos or [])],
            str(ruta),
        )
