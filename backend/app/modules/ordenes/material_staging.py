"""Subida "de una vez" del material a transmitir (audio) — ADR-109.

Router SEPARADO de `adjuntos.py` (aunque usa la MISMA factory,
`build_adjuntos_router`): ese router comparte lista blanca/tope de PDF
(`EXTENSIONES_ADJUNTO_ORDENES`/`s3_max_pdf_bytes`) entre sus 5 tipos — el audio necesita
su PROPIA lista blanca (`EXTENSIONES_AUDIO_ORDENES`, mp3/wav/ogg) y su PROPIO tope
(`S3_MAX_AUDIO_BYTES`, 15 MB), así que no se le agrega como un tipo más de ese router
(forzaría a los 5 tipos existentes a compartir el tope/lista blanca del audio, o al
revés). Se monta en un prefijo de ruta PROPIO (`/material-staging`) para no chocar con
el `/adjuntos` ya montado por ese otro router en el mismo módulo.

Por qué existe: el usuario pidió poder subir el material a transmitir DURANTE la
captura de una OrdenEstacion nueva — antes de que exista un `orden_estacion_id` real
contra el cual colgar un `OrdenEstacionAudio` (mismo problema, mismo mecanismo, que ya
resuelve `adjuntos.py` para el PDF de la Orden de Servicio: `POST /adjuntos?tipo=odc`
sube el archivo a S3 de inmediato y devuelve una CLAVE (`ref`) que se manda como parte
del payload final de creación — nunca un `orden_id` en la URL de subida). Aquí es igual:
el frontend sube cada audio apenas se elige (antes de "Guardar") y junta los `ref`
devueltos; `OrdenEstacionCreate.audios` (ver `orden_estacion.py`) los recibe como lista
y el servicio crea las filas reales de `OrdenEstacionAudio` en el mismo `create()`, en
el orden en que llegaron (el primero = `orden=0` = default).

Si el usuario abandona el formulario sin guardar, el objeto en S3 queda huérfano —
mismo trade-off ya aceptado en `adjuntos.py`/ADR-042 para el PDF de la Orden de Servicio,
no es nuevo de este módulo.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.config import settings
from app.integrations.almacenamiento.documentos import EXTENSIONES_AUDIO_ORDENES
from app.shared.adjuntos_router import build_adjuntos_router


class TipoMaterialStaging(StrEnum):
    AUDIO = "audio"


# Mismo prefijo que ya usa el material a transmitir "real" (`OrdenEstacionAudio.ref`,
# ver `orden_estacion.py#agregar_audio`) — una vez adjunto a la OE, es indistinguible de
# un audio subido por la vía normal (mismo bucket, mismo prefijo, mismo formato de clave).
_PREFIJOS: dict[TipoMaterialStaging, str] = {
    TipoMaterialStaging.AUDIO: "orden_estacion/audios/",
}

router = build_adjuntos_router(
    tag="ordenes:material-staging",
    tipos=TipoMaterialStaging,
    prefijos=_PREFIJOS,
    permiso_subir="ordenes:editar",
    permiso_descargar="ordenes:leer",
    content_disposition="attachment",
    extensiones_permitidas=EXTENSIONES_AUDIO_ORDENES,
    max_bytes=settings.s3_max_audio_bytes,
    prefix="/material-staging",
)
