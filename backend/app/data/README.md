# Datos de referencia

Esta carpeta guarda archivos de datos que el sistema siembra en la base de datos —
no son código ni configuración, son la MATERIA PRIMA de catálogos que necesitan
cargarse desde una fuente externa (a diferencia de los catálogos que el equipo
captura desde la pantalla).

## `sepomex_codigos_postales.csv`

Catálogo de códigos postales de México, para autocompletar los domicilios
estructurados de Anunciante/EmpresaFacturadora (CP → colonia/municipio/estado/ciudad
— ver `backend/app/modules/catalogos/codigo_postal.py`).

- **Fuente:** catálogo público de Correos de México (SEPOMEX), tal como lo redistribuye
  <https://github.com/redrbrt/sepomex-zip-codes> — dato oficial de gobierno, de uso
  libre.
- **Corte:** abril de 2016 (145,908 filas). Los códigos postales cambian con poca
  frecuencia; sigue siendo una base confiable, pero si el equipo detecta un CP real
  que no aparece (colonia nueva), hay que actualizar el archivo.
- **Formato:** CSV, columnas `idEstado,estado,idMunicipio,municipio,ciudad,zona,cp,asentamiento,tipo`.
  Solo se usan `cp`, `asentamiento`, `tipo`, `municipio`, `estado`, `ciudad` — `idEstado`/
  `idMunicipio`/`zona` se ignoran al cargar.
- **Cómo actualizarlo:** reemplazar este archivo (mismo nombre, mismas columnas) y
  volver a correr `python -m scripts.cargar_codigos_postales` — el script BORRA todo
  lo que haya en `asentamiento_postal` y recarga completo desde el CSV.
- **Cuidado con los ceros a la izquierda:** el CSV de origen pierde el "0" inicial de
  algunos CP de Ciudad de México (p. ej. "06700" llega como "6700"). El script de
  carga lo restaura con `.zfill(5)` — si se reemplaza el archivo por otra fuente,
  verificar que ese script siga aplicando.
