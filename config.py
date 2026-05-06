#!/usr/bin/env python3
"""
config.py — Preset management for Ken Burns video generator
Handles loading, merging, and validation of presets from repo and user home.
"""

import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import yaml
except ImportError:
    print("❌  yaml no encontrado. Instálalo con:\n    pip install pyyaml")
    sys.exit(1)


# ── Image helpers ────────────────────────────────────────────────────────────

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

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


def _get_preset_paths() -> tuple:
    """Devuelve rutas de presets (repo, user_home)."""
    repo_preset = Path(__file__).parent / ".ken-burns.yaml"
    user_preset = Path.home() / ".ken-burns.yaml"
    return repo_preset, user_preset


def load_repo_presets() -> Dict[str, Any]:
    """Carga presets base del repositorio."""
    repo_preset, _ = _get_preset_paths()
    
    if not repo_preset.exists():
        print(f"❌  No se encontró .ken-burns.yaml en el repo: {repo_preset}")
        sys.exit(1)
    
    try:
        with open(repo_preset, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data.get('presets', {})
    except Exception as e:
        print(f"❌  Error al parsear .ken-burns.yaml: {e}")
        sys.exit(1)


def load_user_presets() -> Dict[str, Any]:
    """Carga presets personalizados del usuario (si existen)."""
    _, user_preset = _get_preset_paths()
    
    if not user_preset.exists():
        return {}
    
    try:
        with open(user_preset, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not data:
            return {}
        return data.get('presets', {})
    except Exception as e:
        print(f"⚠   Warning: No se pudo leer presets del usuario: {e}")
        print(f"   Archivo: {user_preset}")
        print(f"   Se usarán presets por defecto del repo.\n")
        return {}


def merge_presets(repo: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Fusiona presets: usuario sobrescribe repo."""
    merged = repo.copy()
    merged.update(user)
    return merged


def load_all_presets() -> Dict[str, Any]:
    """Carga y fusiona todos los presets (repo + usuario)."""
    repo = load_repo_presets()
    user = load_user_presets()
    return merge_presets(repo, user)


def get_preset(name: str) -> Optional[Dict[str, Any]]:
    """Obtiene un preset por nombre."""
    presets = load_all_presets()
    if name not in presets:
        return None
    return presets[name]


def list_presets() -> Dict[str, str]:
    """Devuelve dict {nombre: descripción} de todos los presets."""
    presets = load_all_presets()
    return {name: preset.get('description', '—') for name, preset in presets.items()}


def validate_preset(preset: Dict[str, Any]) -> bool:
    """Valida que un preset tenga los campos requeridos."""
    required = {'width', 'height', 'fps', 'intensity', 'description'}
    missing = required - set(preset.keys())
    
    if missing:
        print(f"❌  Preset incompleto. Faltan campos: {missing}")
        return False
    
    # Validar tipos y rangos
    if not isinstance(preset['width'], int) or preset['width'] < 100:
        print(f"❌  width inválido: {preset['width']} (mínimo 100)")
        return False
    
    if not isinstance(preset['height'], int) or preset['height'] < 100:
        print(f"❌  height inválido: {preset['height']} (mínimo 100)")
        return False
    
    if not isinstance(preset['fps'], int) or not (1 <= preset['fps'] <= 120):
        print(f"❌  fps inválido: {preset['fps']} (debe estar entre 1 y 120)")
        return False
    
    if not isinstance(preset['intensity'], (int, float)) or not (0.01 <= preset['intensity'] <= 0.15):
        print(f"❌  intensity inválida: {preset['intensity']} (debe estar entre 0.01 y 0.15)")
        return False
    
    return True


def apply_preset(preset_name: str) -> Dict[str, Any]:
    """Obtiene y valida un preset. Retorna dict listo para usar."""
    preset = get_preset(preset_name)
    
    if not preset:
        print(f"❌  Preset '{preset_name}' no encontrado")
        available = list(list_presets().keys())
        print(f"   Presets disponibles: {', '.join(available)}")
        return None
    
    if not validate_preset(preset):
        return None
    
    # Retornar solo los valores que necesita create_gallery_video
    return {
        'width': preset['width'],
        'height': preset['height'],
        'fps': preset['fps'],
        'intensity': preset['intensity'],
    }


def show_presets_menu() -> None:
    """Muestra lista de presets disponibles en formato bonito."""
    presets = list_presets()
    
    if not presets:
        print("❌  No hay presets disponibles")
        return
    
    print("\n📋 Presets disponibles:\n")
    for i, (name, description) in enumerate(presets.items(), 1):
        print(f"   [{i}] {name:20} — {description}")
    print()


if __name__ == '__main__':
    # Test: mostrar presets disponibles
    print("Testing config.py...\n")
    show_presets_menu()
    
    # Test: aplicar un preset
    youtube = apply_preset('youtube')
    if youtube:
        print(f"✅  Preset 'youtube' aplicado:")
        print(f"   Resolución: {youtube['width']}×{youtube['height']}")
        print(f"   FPS: {youtube['fps']}")
        print(f"   Intensidad: {youtube['intensity']}\n")
