# Logos de los PDFs de Orden interna

Esta carpeta guarda los 2 logotipos que aparecen en el encabezado de los PDFs
generados para "Órdenes internas" (Orden de servicio, Horarios programados,
Horarios reales — ver ADR-043 en `docs/arquitectura.md`).

## Cómo sustituir un logo

Basta con **reemplazar el archivo** manteniendo el mismo nombre:

| Archivo     | Logo                        |
|-------------|------------------------------|
| `oir.jpg`   | OIR (Radiodifusión Nacional) |
| `grc.jpg`   | Grupo Radio Centro           |

No hay que tocar ningún archivo de código ni reiniciar el backend en desarrollo
(el volumen de Docker ya monta esta carpeta en vivo).

- Formatos aceptados: `.jpg`/`.jpeg` o `.png` (el sistema busca ambas extensiones
  con ese mismo nombre — `oir.png` también funciona, por ejemplo).
- Si el archivo no existe, el PDF simplemente se genera sin ese logo (no falla).
- Tamaño recomendado: cualquiera, se escala automáticamente a ~1.1 cm de alto
  conservando su proporción original — usa una imagen con buena resolución para
  que no se vea pixelada al imprimir.
