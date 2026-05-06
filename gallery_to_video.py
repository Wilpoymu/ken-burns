#!/usr/bin/env python3
"""
gallery_to_video.py — Galería de imágenes numeradas → Video con efecto Ken Burns sutil
══════════════════════════════════════════════════════════════════════════════

INSTALACIÓN:
    pip install moviepy Pillow numpy

USO:
    python gallery_to_video.py <CARPETA> --duration <SEG> [--all | --even | --odd] [opciones]
    python gallery_to_video.py <CARPETA> --audio <ARCHIVO_AUDIO> [--all | --even | --odd] [opciones]

ARGUMENTOS:
    CARPETA             Carpeta con las imágenes
    --duration, -d      Duración total del video en segundos (requerido si no usas --audio)
    --audio, -a         Archivo de audio; si se usa, la duración del video se toma del audio
    --all, -A           Usar TODAS las imágenes (sin filtro)
    --even, -e          Usar imágenes de número PAR   (2, 4, 6 ...)
    --odd,  -i          Usar imágenes de número IMPAR (1, 3, 5 ...)
    --output, -o        Archivo de salida (default: gallery_video.mp4)
    --width             Ancho del video en píxeles  (default: 1920)
    --height            Alto  del video en píxeles  (default: 1080)
    --fps               Fotogramas por segundo       (default: 30)
    --intensity         Intensidad del movimiento 0.01–0.10 (default: 0.04)
    --seed              Semilla aleatoria para reproducibilidad (default: 42)

EJEMPLOS:
    python gallery_to_video.py ./fotos --duration 60 --all
    python gallery_to_video.py ./fotos --audio narracion.mp3 --even
    python gallery_to_video.py ./fotos --duration 120 --odd --output mi_video.mp4
    python gallery_to_video.py ./fotos --duration 30  --all --width 1280 --height 720
    python gallery_to_video.py ./fotos --duration 90  --odd  --intensity 0.06 --fps 24

NOMENCLATURA ESPERADA (número en el nombre, con patrón):
    01_foto.jpg  escena_01.png  10_ciudad.jpg  escena_22_atardecer.webp ...

MOVIMIENTOS (asignados aleatoriamente, reproducibles con --seed):
    zoom_in · zoom_out · pan_right · pan_left · pan_up · pan_down
"""

import os
import re
import sys
import random
import argparse
import textwrap
import numpy as np
from pathlib import Path
from PIL import Image

# ── Compatibilidad Pillow (resample constants cambiaron en v10) ──────────────
try:
    _LANCZOS   = Image.Resampling.LANCZOS
    _BILINEAR  = Image.Resampling.BILINEAR
except AttributeError:
    _LANCZOS   = Image.LANCZOS    # type: ignore[attr-defined]
    _BILINEAR  = Image.BILINEAR   # type: ignore[attr-defined]

# ── Compatibilidad moviepy v1 / v2 ──────────────────────────────────────────
def _import_moviepy():
    try:
        import moviepy.editor as mpy      # v1
        return mpy
    except ImportError:
        pass
    try:
        import moviepy                     # v2 fallback
        return moviepy
    except ImportError:
        print("❌  moviepy no encontrado. Instálalo con:\n    pip install moviepy")
        sys.exit(1)

mpy = _import_moviepy()

# ── Constantes ───────────────────────────────────────────────────────────────
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
MOVEMENTS = ['zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'pan_up', 'pan_down']


# ════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════

def get_numbered_images(folder: str, filter_mode: str = 'all') -> list:
    """
    Devuelve las rutas de imágenes que contengan números en el nombre,
    filtradas por modo (all/even/odd) y ordenadas ascendentemente.
    
    Soporta patrones como:
      - 01_foto.jpg  (número al inicio)
      - escena_01.png  (nombre_número)
      - escena_01_texto.jpg  (nombre_número_más_texto)
    
    Args:
        folder: Carpeta con las imágenes
        filter_mode: 'all' (todas), 'even' (pares), 'odd' (impares)
    """
    items = []
    for fname in os.listdir(folder):
        if Path(fname).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        # Regex: busca números en el nombre (al inicio o después de _)
        m = re.search(r'(?:^|_)(\d+)', fname)
        if not m:
            continue
        num = int(m.group(1))
        
        # Aplicar filtro por paridad
        if filter_mode == 'all':
            items.append((num, os.path.join(folder, fname)))
        elif filter_mode == 'even' and num % 2 == 0:
            items.append((num, os.path.join(folder, fname)))
        elif filter_mode == 'odd' and num % 2 != 0:
            items.append((num, os.path.join(folder, fname)))

    items.sort(key=lambda x: x[0])
    return [path for _, path in items]


def load_canvas(image_path: str, canvas_w: int, canvas_h: int) -> np.ndarray:
    """
    Carga la imagen y la redimensiona con "cover fit" (rellena el canvas
    sin dejar bordes negros, centrando el recorte).
    """
    img = Image.open(image_path).convert('RGB')

    img_ratio    = img.width  / img.height
    canvas_ratio = canvas_w   / canvas_h

    if img_ratio > canvas_ratio:          # imagen más ancha: ajustar altura
        new_h = canvas_h
        new_w = int(new_h * img_ratio)
    else:                                  # imagen más alta: ajustar ancho
        new_w = canvas_w
        new_h = int(new_w / img_ratio)

    if new_w < canvas_w or new_h < canvas_h:
        print(f"    ⚠  Imagen pequeña ({img.width}×{img.height}) → se escalará a {new_w}×{new_h}")

    img = img.resize((new_w, new_h), _LANCZOS)

    x_off = (new_w - canvas_w) // 2
    y_off = (new_h - canvas_h) // 2
    img   = img.crop((x_off, y_off, x_off + canvas_w, y_off + canvas_h))

    return np.array(img, dtype=np.uint8)


def ease_smooth(t: float) -> float:
    """Smoothstep: suave al inicio y al final, sin aceleración brusca."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def get_crop_windows(movement: str, out_w: int, out_h: int,
                     canvas_w: int, canvas_h: int):
    """
    Devuelve (start, end) donde cada uno es (x, y, width, height) del
    recorte sobre el canvas para el fotograma inicial y final del clip.
    """
    mx = canvas_w - out_w   # margen horizontal total
    my = canvas_h - out_h   # margen vertical total
    cx = mx // 2             # centro horizontal
    cy = my // 2             # centro vertical

    if movement == 'zoom_in':
        start = (0,  0,  canvas_w, canvas_h)   # campo amplio → recortado
        end   = (cx, cy, out_w,    out_h)
    elif movement == 'zoom_out':
        start = (cx, cy, out_w,    out_h)       # recortado → campo amplio
        end   = (0,  0,  canvas_w, canvas_h)
    elif movement == 'pan_right':
        start = (0,  cy, out_w, out_h)
        end   = (mx, cy, out_w, out_h)
    elif movement == 'pan_left':
        start = (mx, cy, out_w, out_h)
        end   = (0,  cy, out_w, out_h)
    elif movement == 'pan_up':
        start = (cx, 0,  out_w, out_h)
        end   = (cx, my, out_w, out_h)
    else:  # pan_down
        start = (cx, my, out_w, out_h)
        end   = (cx, 0,  out_w, out_h)

    return start, end


# ════════════════════════════════════════════════════════════════════════════
#  Generador de clip por imagen
# ════════════════════════════════════════════════════════════════════════════

def build_clip(image_path: str, clip_duration: float, output_size: tuple,
               intensity: float, movement_seed: int):
    """
    Crea un VideoClip de moviepy para una imagen.
    La imagen se pre-carga una vez; los fotogramas se generan bajo demanda
    (streaming) para mantener el uso de RAM bajo durante el renderizado.
    """
    out_w, out_h = output_size
    margin_x = int(out_w * intensity)
    margin_y = int(out_h * intensity)
    canvas_w = out_w + margin_x * 2
    canvas_h = out_h + margin_y * 2

    # Pre-carga (una sola vez por imagen)
    canvas = load_canvas(image_path, canvas_w, canvas_h)

    # Movimiento reproducible por semilla
    rng      = random.Random(movement_seed)
    movement = rng.choice(MOVEMENTS)

    start_crop, end_crop = get_crop_windows(movement, out_w, out_h, canvas_w, canvas_h)

    # Captura explícita de variables para evitar el problema de closure en loops
    def make_frame(t,
                   _canvas=canvas, _start=start_crop, _end=end_crop,
                   _dur=clip_duration, _ow=out_w, _oh=out_h,
                   _cw=canvas_w, _ch=canvas_h):

        progress = t / max(_dur, 1e-9)
        eased    = ease_smooth(progress)

        # Interpolar ventana de recorte
        x  = int(_start[0] + (_end[0] - _start[0]) * eased)
        y  = int(_start[1] + (_end[1] - _start[1]) * eased)
        cw = int(_start[2] + (_end[2] - _start[2]) * eased)
        ch = int(_start[3] + (_end[3] - _start[3]) * eased)

        # Clamp para no salir del canvas
        cw = max(1, min(cw, _cw))
        ch = max(1, min(ch, _ch))
        x  = max(0, min(x,  _cw - cw))
        y  = max(0, min(y,  _ch - ch))

        crop = _canvas[y:y + ch, x:x + cw]

        # Redimensionar solo cuando el tamaño del recorte difiere del output
        # (ocurre en movimientos de zoom; en paneo el tamaño es constante)
        if cw != _ow or ch != _oh:
            frame = np.array(Image.fromarray(crop).resize((_ow, _oh), _BILINEAR))
        else:
            frame = crop

        return frame

    return mpy.VideoClip(make_frame, duration=clip_duration)


def load_audio(audio_path: str):
    """Carga un archivo de audio con moviepy y devuelve (clip, duracion_seg)."""
    clip = mpy.AudioFileClip(audio_path)
    duration = float(getattr(clip, 'duration', 0.0) or 0.0)
    if duration <= 0:
        clip.close()
        raise ValueError(f"No se pudo leer una duración válida del audio: {audio_path}")
    return clip, duration


def attach_audio(video_clip, audio_clip):
    """Compatibilidad moviepy v1/v2 para asignar pista de audio al video."""
    if hasattr(video_clip, 'set_audio'):
        return video_clip.set_audio(audio_clip)
    if hasattr(video_clip, 'with_audio'):
        return video_clip.with_audio(audio_clip)
    raise RuntimeError("La versión actual de moviepy no soporta adjuntar audio")


# ════════════════════════════════════════════════════════════════════════════
#  Función principal
# ════════════════════════════════════════════════════════════════════════════

def create_gallery_video(
        image_folder:  str,
        total_duration: float | None,
        output_path:   str,
        filter_mode:   str  = 'all',
        output_size:   tuple = (1920, 1080),
        fps:           int   = 30,
        intensity:     float = 0.04,
        seed:          int   = 42,
        audio_path:    str | None = None):

    images = get_numbered_images(image_folder, filter_mode)

    if not images:
        mode_names = {'all': 'todas', 'even': 'pares', 'odd': 'impares'}
        mode_desc = mode_names.get(filter_mode, filter_mode)
        print(f"\n❌  No se encontraron imágenes con números ({mode_desc}) en: {image_folder}")
        print("    Asegúrate de que los archivos contengan números (ej: 01_foto.jpg o escena_01.png)")
        sys.exit(1)

    n          = len(images)
    mode_names = {'all': 'todas', 'even': 'pares', 'odd': 'impares'}
    parity_str = mode_names.get(filter_mode, filter_mode)

    audio_clip = None
    audio_clip_for_video = None
    if audio_path:
        input_duration = total_duration
        try:
            audio_clip, audio_duration = load_audio(audio_path)
        except Exception as exc:
            print(f"\n❌  Error al cargar el audio: {exc}")
            sys.exit(1)
        total_duration = audio_duration
        print(f"  🎵  Audio detectado    : {os.path.basename(audio_path)}")
        print(f"  ⏱   Duración del audio : {total_duration:.2f} s")
        if input_duration is not None:
            print("  ℹ   Se ignorará --duration porque se usa la duración real del audio")
    elif total_duration is None:
        print("\n❌  Debes indicar --duration o proporcionar --audio")
        sys.exit(1)

    dur_each = total_duration / n

    print(f"\n{'━' * 60}")
    print(f"  🖼   Imágenes ({parity_str}): {n}")
    for i, p in enumerate(images, 1):
        print(f"       {i:3d}. {os.path.basename(p)}")
    print(f"{'━' * 60}")
    print(f"  ⏱   Duración total    : {total_duration:.2f} s")
    print(f"  ⏱   Duración/imagen   : {dur_each:.4f} s  ({dur_each * fps:.1f} frames)")
    print(f"  📐  Resolución        : {output_size[0]}×{output_size[1]} @ {fps} fps")
    print(f"  🎯  Intensidad mov.   : {intensity * 100:.1f} %")
    print(f"  🌱  Semilla           : {seed}")
    print(f"{'━' * 60}\n")

    # ── Crear clips ──────────────────────────────────────────────────────────
    print("⚙   Preparando clips…")
    clips = []
    for i, img_path in enumerate(images):
        print(f"    [{i+1:3d}/{n}]  {os.path.basename(img_path)}")
        clip = build_clip(img_path, dur_each, output_size, intensity, seed + i)
        clips.append(clip)

    # ── Concatenar ───────────────────────────────────────────────────────────
    print(f"\n🔗  Concatenando {n} clips…")
    final = clips[0] if n == 1 else mpy.concatenate_videoclips(clips, method='chain')

    # Ajustar y adjuntar audio si se proporcionó
    if audio_clip is not None:
        if hasattr(audio_clip, 'subclipped'):
            audio_clip_for_video = audio_clip.subclipped(0, total_duration)
        else:
            audio_clip_for_video = audio_clip.subclip(0, total_duration)
        final = attach_audio(final, audio_clip_for_video)

    # ── Renderizar ───────────────────────────────────────────────────────────
    print(f"🎬  Renderizando → {output_path}\n")
    final.write_videofile(
        output_path,
        fps=fps,
        codec='libx264',
        audio=audio_clip is not None,
        audio_codec='aac' if audio_clip is not None else None,
        threads=min(os.cpu_count() or 4, 8),
        ffmpeg_params=['-crf', '18', '-preset', 'fast'],
        logger='bar',
    )

    # ── Liberar memoria ──────────────────────────────────────────────────────
    final.close()
    for c in clips:
        c.close()
    if audio_clip_for_video is not None and audio_clip_for_video is not audio_clip:
        audio_clip_for_video.close()
    if audio_clip is not None:
        audio_clip.close()

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n✅  Video guardado: {output_path}")
    print(f"    Tamaño   : {size_mb:.1f} MB")
    print(f"    Duración : {total_duration:.2f} s  |  Frames esperados: {int(total_duration * fps)}")


# ════════════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog='gallery_to_video',
        description='🎬  Convierte una galería de imágenes en video con efecto Ken Burns sutil',
        formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog=textwrap.dedent('''\
                Ejemplos:
                    python gallery_to_video.py ./fotos --duration 60 --even
                    python gallery_to_video.py ./fotos --audio narracion.mp3 --even
                    python gallery_to_video.py ./fotos --duration 120 --odd --output mi_video.mp4
                    python gallery_to_video.py ./fotos --duration 30  --even --width 1280 --height 720
                    python gallery_to_video.py ./fotos --duration 90  --odd  --intensity 0.06 --fps 24
                    python gallery_to_video.py ./fotos --duration 60  --even --seed 7

                Nomenclatura esperada de archivos:
                    01_foto.jpg   02_playa.png   10_ciudad.jpg   22_atardecer.webp ...
                '''),
    )

    parser.add_argument('folder', metavar='CARPETA',
                        help='Carpeta que contiene las imágenes')
    parser.add_argument('--duration', '-d', type=float,
                        metavar='SEG',
                        help='Duración total del video en segundos (requerido si no usas --audio)')
    parser.add_argument('--audio', '-a', nargs='+',
                        metavar='ARCHIVO_AUDIO',
                        help='Ruta de audio para incluir en el video; su duración define el tiempo total')
    parser.add_argument('--output', '-o', default='gallery_video.mp4',
                        metavar='ARCHIVO',
                        help='Ruta del video de salida  (default: gallery_video.mp4)')

    parity = parser.add_mutually_exclusive_group()
    parity.add_argument('--all', '-A', action='store_true',
                        help='Usar TODAS las imágenes (sin filtro de paridad)')
    parity.add_argument('--even', '-e', action='store_true',
                        help='Usar imágenes con número PAR   (2, 4, 6 …)')
    parity.add_argument('--odd',  '-i', action='store_true',
                        help='Usar imágenes con número IMPAR (1, 3, 5 …)')

    parser.add_argument('--width',  type=int,   default=1920,
                        help='Ancho del video en píxeles  (default: 1920)')
    parser.add_argument('--height', type=int,   default=1080,
                        help='Alto  del video en píxeles  (default: 1080)')
    parser.add_argument('--fps',    type=int,   default=30,
                        help='Fotogramas por segundo       (default: 30)')
    parser.add_argument('--intensity', type=float, default=0.04,
                        metavar='0.01-0.10',
                        help='Intensidad del movimiento    (default: 0.04 = 4%%)')
    parser.add_argument('--seed',   type=int,   default=42,
                        help='Semilla para reproducibilidad (default: 42)')

    args = parser.parse_args()

    # Normalizar audio para tolerar rutas con espacios sin comillas en CLI
    audio_path = ' '.join(args.audio).strip() if args.audio else None

    # Validaciones básicas
    if not os.path.isdir(args.folder):
        parser.error(f"La carpeta no existe: {args.folder}")
    if args.duration is None and not audio_path:
        parser.error("Debes indicar --duration o --audio")
    if args.duration is not None and args.duration <= 0:
        parser.error("La duración debe ser mayor a 0")
    if audio_path and not os.path.isfile(audio_path):
        parser.error(f"El archivo de audio no existe: {audio_path}")
    if not (1 <= args.fps <= 120):
        parser.error("Los FPS deben estar entre 1 y 120")

    # Determinar modo de filtro (interactivo si no se especificó)
    if not args.all and not args.even and not args.odd:
        print("\n¿Qué imágenes deseas usar?")
        print("  [t]  Todas   (01, 02, 03, 04 …)")
        print("  [p]  Pares   (02, 04, 06, 08 …)")
        print("  [i]  Impares (01, 03, 05, 07 …)")
        while True:
            choice = input("Opción [t/p/i]: ").strip().lower()
            if choice in ('t', 'todas', 'all', 'a'):
                filter_mode = 'all'
                break
            elif choice in ('p', 'par', 'pares', 'even', 'e'):
                filter_mode = 'even'
                break
            elif choice in ('i', 'impar', 'impares', 'odd', 'o'):
                filter_mode = 'odd'
                break
            print("  → Escribe 't' para todas, 'p' para pares o 'i' para impares")
    else:
        if args.all:
            filter_mode = 'all'
        elif args.even:
            filter_mode = 'even'
        else:  # args.odd
            filter_mode = 'odd'

    intensity = max(0.01, min(0.15, args.intensity))
    if intensity != args.intensity:
        print(f"⚠   Intensidad ajustada a {intensity:.2f} (rango válido: 0.01–0.15)")

    create_gallery_video(
        image_folder   = args.folder,
        total_duration = args.duration,
        output_path    = args.output,
        filter_mode    = filter_mode,
        output_size    = (args.width, args.height),
        fps            = args.fps,
        intensity      = intensity,
        seed           = args.seed,
        audio_path     = audio_path,
    )


if __name__ == '__main__':
    main()
