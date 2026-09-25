"""Pruebas de la capa de integración de correo (`app/integrations/correo/`).

Cubre: `construir_mime` (destinatario único y lista, adjuntos), y ADR-122 —
`CorreoLocal` guarda un `.eml` real (parseable, con asunto/cuerpo/adjuntos correctos) en
vez de solo loguear, para poder revisar el mensaje armado sin depender de SES/AWS.
"""

from __future__ import annotations

import email
from email.header import decode_header
from pathlib import Path

from app.integrations.correo.adapter_local import CorreoLocal
from app.integrations.correo.mime import construir_mime


def test_construir_mime_un_destinatario_y_adjuntos() -> None:
    mensaje = construir_mime(
        remitente="de@x.com",
        destinatario="para@x.com",
        asunto="Asunto de prueba",
        cuerpo_texto="Cuerpo de prueba.",
        adjuntos=[("archivo.pdf", b"contenido-pdf", "application/pdf")],
    )
    assert mensaje["Subject"] == "Asunto de prueba"
    assert mensaje["From"] == "de@x.com"
    assert mensaje["To"] == "para@x.com"
    partes = mensaje.get_payload()
    assert len(partes) == 2  # cuerpo de texto + 1 adjunto


def test_construir_mime_varios_destinatarios_va_en_to_separado_por_coma() -> None:
    mensaje = construir_mime(
        remitente="de@x.com",
        destinatario=["uno@x.com", "dos@x.com"],
        asunto="Asunto",
        cuerpo_texto="Cuerpo",
    )
    assert mensaje["To"] == "uno@x.com, dos@x.com"


def test_correo_local_guarda_eml_real(tmp_path: Path) -> None:
    correo = CorreoLocal(tmp_path)
    correo.enviar(
        destinatario="contacto@afiliado.com",
        asunto="Orden de Transmisión",
        cuerpo_texto="Se adjunta el material.",
        adjuntos=[
            ("horarios_programados.pdf", b"%PDF-falso", "application/pdf"),
            ("material.mp3", b"audio-falso", "audio/mpeg"),
        ],
    )

    carpeta = tmp_path / "correos_simulados"
    archivos = list(carpeta.glob("*.eml"))
    assert len(archivos) == 1

    contenido = archivos[0].read_bytes()
    mensaje = email.message_from_bytes(contenido)
    trozo, codificacion = decode_header(mensaje["Subject"])[0]
    asunto = trozo.decode(codificacion or "ascii") if isinstance(trozo, bytes) else trozo
    assert asunto == "Orden de Transmisión"
    assert mensaje["To"] == "contacto@afiliado.com"

    nombres_adjuntos = [
        parte.get_filename() for parte in mensaje.walk() if parte.get_filename()
    ]
    assert "horarios_programados.pdf" in nombres_adjuntos
    assert "material.mp3" in nombres_adjuntos


def test_correo_local_no_falla_sin_destinatarios_para_el_nombre_de_archivo(tmp_path: Path) -> None:
    correo = CorreoLocal(tmp_path)
    correo.enviar(destinatario=[], asunto="Sin destinatarios", cuerpo_texto="Cuerpo")

    archivos = list((tmp_path / "correos_simulados").glob("*.eml"))
    assert len(archivos) == 1
