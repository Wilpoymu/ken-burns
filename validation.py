#!/usr/bin/env python3
"""
validation.py — Pre-validation checks for Ken Burns generator
Validates images, audio, and FFmpeg before rendering starts.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Tuple, List, Optional

try:
    from PIL import Image
except ImportError:
    print("❌  Pillow no encontrado. Instálalo con:\n    pip install Pillow")
    sys.exit(1)

try:
    import moviepy.editor as mpy
except ImportError:
    try:
        import moviepy
        mpy = moviepy
    except ImportError:
        print("❌  moviepy no encontrado. Instálalo con:\n    pip install moviepy")
        sys.exit(1)


# ── Image validation ─────────────────────────────────────────────────────────

def validate_images_early(image_paths: List[str]) -> Tuple[int, List[str]]:
    """
    Pre-valida imágenes ANTES de renderizar.
    
    Devuelve: (valid_count, warning_list)
    - valid_count: cantidad de imágenes que abrieron ok
    - warning_list: lista de warnings (imagen pequeña, etc.)
    """
    warnings = []
    valid_count = 0
    
    if not image_paths:
        return 0, ["No hay imágenes para validar"]
    
    print("🔍 Pre-validando imágenes...\n")
    
    for i, img_path in enumerate(image_paths, 1):
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                
                # Validación 1: Imagen exists and can open
                valid_count += 1
                
                # Validación 2: Check minimum resolution
                MIN_WIDTH, MIN_HEIGHT = 800, 600
                if width < MIN_WIDTH or height < MIN_HEIGHT:
                    msg = f"   ⚠   [{i:3d}] {Path(img_path).name} — Pequeña ({width}×{height}, mín: {MIN_WIDTH}×{MIN_HEIGHT})"
                    warnings.append(msg)
                    print(msg)
                else:
                    print(f"   ✅  [{i:3d}] {Path(img_path).name} — {width}×{height}")
        
        except Exception as e:
            msg = f"   ⚠   [{i:3d}] {Path(img_path).name} — Corrupta o no readable: {type(e).__name__}"
            warnings.append(msg)
            print(msg)
    
    print()
    return valid_count, warnings


def check_ffmpeg() -> Tuple[bool, str]:
    """
    Verifica que FFmpeg esté en PATH y sea functional.
    
    Devuelve: (is_available, version_string)
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode == 0:
            # Extraer primera línea con versión
            output = result.stdout.decode('utf-8', errors='ignore')
            first_line = output.split('\n')[0]
            return True, first_line
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    return False, ""


def validate_ffmpeg() -> bool:
    """Valida FFmpeg y retorna True si está ok, False si falta."""
    is_available, version = check_ffmpeg()
    
    if not is_available:
        print("❌ FFmpeg no encontrado en PATH")
        print("   Solución:")
        print("   - Windows: corre ./install_ffmpeg_windows.ps1")
        print("   - macOS: brew install ffmpeg")
        print("   - Linux: sudo apt install ffmpeg")
        print()
        return False
    
    print(f"✅ FFmpeg disponible: {version}\n")
    return True


# ── Audio validation ─────────────────────────────────────────────────────────

def validate_audio(audio_path: str) -> Tuple[bool, Optional[float], str]:
    """
    Pre-valida archivo de audio.
    
    Devuelve: (is_valid, duration_in_seconds, error_message)
    """
    if not audio_path:
        return True, None, ""
    
    print("🔍 Pre-validando audio...\n")
    
    # Check 1: El archivo existe
    if not os.path.isfile(audio_path):
        msg = f"   ❌ Archivo no encontrado: {audio_path}"
        print(msg)
        return False, None, msg
    
    print(f"   ✅ Archivo existe: {Path(audio_path).name}")
    
    # Check 2: moviepy puede leerlo
    try:
        audio_clip = mpy.AudioFileClip(audio_path)
        duration = float(getattr(audio_clip, 'duration', 0.0) or 0.0)
        audio_clip.close()
        
        if duration <= 0:
            msg = f"   ❌ No se pudo leer duración válida del audio"
            print(msg)
            return False, None, msg
        
        print(f"   ✅ Duración: {duration:.2f} segundos")
        print()
        return True, duration, ""
    
    except Exception as e:
        msg = f"   ❌ FFmpeg no puede leer este audio: {e}"
        print(msg)
        print(f"   Formatos soportados: MP3, WAV, AAC, M4A, FLAC")
        print(f"   Intenta convertir: ffmpeg -i {Path(audio_path).name} -q:a 0 -map a output.mp3")
        print()
        return False, None, msg


# ── Folder validation ────────────────────────────────────────────────────────

def validate_folder(folder_path: str) -> bool:
    """Verifica que la carpeta exista."""
    if not os.path.isdir(folder_path):
        print(f"❌ Carpeta no existe: {folder_path}\n")
        return False
    
    print(f"✅ Carpeta existe: {folder_path}\n")
    return True


# ── Pre-validation suite ─────────────────────────────────────────────────────

def run_pre_validation(
        folder: str,
        image_paths: List[str],
        audio_path: Optional[str] = None
) -> bool:
    """
    Ejecuta toda la pre-validación antes del renderizado.
    Retorna: True si todo ok, False si hay problemas críticos.
    """
    print("\n" + "━" * 60)
    print("  PRE-VALIDACIÓN")
    print("━" * 60 + "\n")
    
    # 1. FFmpeg availability (crítico)
    if not validate_ffmpeg():
        return False
    
    # 2. Folder exists
    if not validate_folder(folder):
        return False
    
    # 3. Images
    if image_paths:
        valid_count, img_warnings = validate_images_early(image_paths)
        if valid_count == 0:
            print("❌ Ninguna imagen pudo validarse. Abort.\n")
            return False
    
    # 4. Audio (optional)
    if audio_path:
        audio_ok, duration, audio_msg = validate_audio(audio_path)
        if not audio_ok:
            print("❌ Audio inválido. Abort.\n")
            return False
    
    print("━" * 60)
    print("  ✅ PRE-VALIDACIÓN COMPLETADA")
    print("━" * 60 + "\n")
    return True


if __name__ == '__main__':
    # Test: validación de FFmpeg
    print("Testing validation.py...\n")
    validate_ffmpeg()
