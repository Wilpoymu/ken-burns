# gallery_to_video.py

Convierte una galería de imágenes numeradas en un video con **efecto Ken Burns sutil** (zoom y paneo muy leves), distribuyendo cada imagen en intervalos de tiempo iguales dentro de la duración total deseada.

También puede recibir un archivo de audio: el script detecta automáticamente cuántos segundos dura, reparte las escenas en tiempos iguales y exporta el video final con el audio incluido.

---

## Instalación

```bash
pip install moviepy Pillow numpy
```

> **Nota:** también necesitas tener **ffmpeg** instalado en el sistema.
> - macOS:   `brew install ffmpeg`
> - Ubuntu:  `sudo apt install ffmpeg`
> - Windows: descarga desde https://ffmpeg.org/download.html y agrégalo al PATH

---

## Nomenclatura esperada de archivos

Los archivos deben comenzar con un número (con o sin ceros a la izquierda):

```
01_playa.jpg
02_ciudad.png
03_atardecer.jpg
04_bosque.webp
10_montaña.tiff
```

Los archivos **sin número al inicio** son ignorados automáticamente.

---

## Uso básico

```bash
# Usar imágenes pares (02, 04, 06…), video de 60 segundos
python gallery_to_video.py ./fotos --duration 60 --even

# Usar imágenes impares (01, 03, 05…), video de 2 minutos
python gallery_to_video.py ./fotos --duration 120 --odd --output mi_video.mp4

# Usar un audio: la duración total se toma del audio automáticamente
python gallery_to_video.py ./fotos --audio narracion.mp3 --even --output video_con_audio.mp4

# Sin flag --even/--odd: el script preguntará interactivamente
python gallery_to_video.py ./fotos --duration 90
```

---

## Todos los parámetros

| Parámetro | Valor por defecto | Descripción |
|-----------|-------------------|-------------|
| `CARPETA` | *(requerido)* | Carpeta con las imágenes |
| `--duration` / `-d` | *(requerido si no usas `--audio`)* | Duración total del video en segundos |
| `--audio` / `-a` | — | Ruta del audio a incluir; su duración define el tiempo total del video |
| `--even` / `-e` | — | Usar imágenes con número **par** |
| `--odd` / `-i` | — | Usar imágenes con número **impar** |
| `--output` / `-o` | `gallery_video.mp4` | Archivo de salida |
| `--width` | `1920` | Ancho del video en píxeles |
| `--height` | `1080` | Alto del video en píxeles |
| `--fps` | `30` | Fotogramas por segundo |
| `--intensity` | `0.04` (4 %) | Intensidad del movimiento (0.01–0.10) |
| `--seed` | `42` | Semilla aleatoria para reproducibilidad |

---

## Ejemplos avanzados

```bash
# HD 720p, 24fps, movimiento más perceptible
python gallery_to_video.py ./fotos --duration 45 --even \
    --width 1280 --height 720 --fps 24 --intensity 0.07

# Resultado reproducible con semilla fija
python gallery_to_video.py ./fotos --duration 60 --odd --seed 123

# Video sincronizado al audio (escenas iguales + audio embebido)
python gallery_to_video.py ./fotos --audio musica.mp3 --odd --seed 123

# Cuadrado para redes sociales (1:1)
python gallery_to_video.py ./fotos --duration 30 --even \
    --width 1080 --height 1080

# Vertical para Reels/TikTok (9:16)
python gallery_to_video.py ./fotos --duration 30 --even \
    --width 1080 --height 1920
```

---

## Cómo funciona el efecto Ken Burns

Para cada imagen se elige aleatoriamente uno de 6 movimientos:

| Movimiento | Descripción |
|------------|-------------|
| `zoom_in`  | La imagen se acerca suavemente |
| `zoom_out` | La imagen se aleja suavemente |
| `pan_right` | La imagen se desplaza hacia la derecha |
| `pan_left`  | La imagen se desplaza hacia la izquierda |
| `pan_up`    | La imagen sube |
| `pan_down`  | La imagen baja |

- El movimiento usa **suavizado smoothstep** (sin arranques ni frenazos bruscos).
- La imagen se pre-carga con un canvas ligeramente más grande que el output para permitir el movimiento sin bordes negros.
- Los frames se generan **bajo demanda** (streaming), manteniendo el uso de RAM bajo.

---

## Calidad del video

El script usa el codec **H.264** con `CRF 18` (alta calidad, casi sin pérdida visible) y preset `fast` para un buen balance calidad/velocidad de renderizado.
