#!/usr/bin/env python3
"""
Servidor web local para Ken Burns: UI en navegador, cola persistente y renders vía gallery_to_video.py.
Uso: python web/app.py  →  http://127.0.0.1:5050
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import uuid
import zipfile
from collections import deque
from pathlib import Path
from typing import Any

# Con `python web/app.py`, sys.path no incluye la raíz del repo y falla `import web`.
REPO_ROOT = Path(__file__).resolve().parent.parent
_sr = str(REPO_ROOT)
if _sr not in sys.path:
    sys.path.insert(0, _sr)

import yaml
from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from web.job_store import init_db, insert_job, get_job, list_jobs, recover_after_restart, update_job

SCRIPT = REPO_ROOT / "gallery_to_video.py"
OUTPUT_DIR = REPO_ROOT / "outputs"
UPLOAD_ROOT = REPO_ROOT / "uploads"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024

_job_fifo: queue.Queue[str] = queue.Queue()
_worker_started = False

YAML_REPO = REPO_ROOT / ".ken-burns.yaml"
YAML_USER = Path.home() / ".ken-burns.yaml"


def _tail_from_buf(buf: deque[str], max_chars: int = 12000) -> str:
    text = "".join(buf)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _validate_folder(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        raise ValueError("La carpeta de imágenes debe ser una ruta absoluta.")
    p = p.resolve()
    if not p.is_dir():
        raise ValueError("La carpeta de imágenes no existe o no es un directorio.")
    return p


def _validate_audio(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        raise ValueError("La ruta de audio debe ser absoluta.")
    p = p.resolve()
    if not p.is_file():
        raise ValueError("El archivo de audio no existe.")
    return p


def load_yaml_presets_merged() -> dict[str, Any]:
    """Lee presets repo + usuario sin usar config.sys.exit."""
    repo_presets: dict[str, Any] = {}
    if YAML_REPO.is_file():
        with open(YAML_REPO, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        repo_presets = data.get("presets") or {}
    user_presets: dict[str, Any] = {}
    if YAML_USER.is_file():
        try:
            with open(YAML_USER, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            user_presets = data.get("presets") or {}
        except OSError:
            pass
    merged = dict(repo_presets)
    merged.update(user_presets)
    return merged


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path, max_files: int = 2500, max_uncompressed: int = 600 * 1024 * 1024) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    total_uncompressed = 0
    members = [m for m in zf.infolist() if not m.is_dir()]
    if len(members) > max_files:
        raise ValueError(f"El ZIP tiene demasiados archivos (máx. {max_files}).")
    for m in members:
        total_uncompressed += int(m.file_size)
        if total_uncompressed > max_uncompressed:
            raise ValueError("El ZIP descomprimido supera el tamaño máximo permitido.")
        raw = m.filename
        if raw.startswith("/") or ".." in Path(raw).parts:
            raise ValueError("El ZIP contiene rutas no permitidas.")
        target = (dest / raw).resolve()
        try:
            target.relative_to(dest.resolve())
        except ValueError:
            raise ValueError("El ZIP contiene rutas inválidas (path traversal).") from None
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(m, "r") as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def _save_flat_images(files: list[Any], dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    used_names: dict[str, int] = {}
    for fs in files:
        fn = fs.filename or ""
        if not fn:
            continue
        base = Path(fn).name
        safe = secure_filename(base) or f"file_{count}"
        ext = Path(safe).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        stem = Path(safe).stem
        ext_part = Path(safe).suffix
        candidate = safe
        if candidate in used_names:
            used_names[candidate] += 1
            candidate = f"{stem}_{used_names[candidate]}{ext_part}"
        else:
            used_names[candidate] = 0
        path = dest / candidate
        fs.save(path)
        count += 1
    return count


def _build_cmd(
    folder: Path,
    output_path: Path,
    *,
    audio_path: Path | None,
    duration_f: float | None,
    filter_mode: str,
    width: int,
    height: int,
    fps: int,
    intensity: float,
    seed: int,
) -> list[str]:
    cmd: list[str] = [
        sys.executable,
        str(SCRIPT),
        str(folder),
        "--output",
        str(output_path),
        "--width",
        str(width),
        "--height",
        str(height),
        "--fps",
        str(fps),
        "--intensity",
        str(intensity),
        "--seed",
        str(seed),
    ]
    if audio_path is not None:
        cmd.extend(["--audio", str(audio_path)])
    else:
        assert duration_f is not None
        cmd.extend(["--duration", str(duration_f)])

    if filter_mode == "all":
        cmd.append("--all")
    elif filter_mode == "even":
        cmd.append("--even")
    else:
        cmd.append("--odd")
    return cmd


def _run_job_subprocess(job_id: str) -> None:
    row = get_job(job_id)
    if not row:
        return
    cmd = json.loads(row["cmd_json"])
    upload_dir = row["upload_dir"]
    buf: deque[str] = deque(maxlen=800)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    update_job(job_id, status="running", message="Render en curso…")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            buf.append(line)
            update_job(job_id, log_tail=_tail_from_buf(buf))
        code = proc.wait()
        tail = _tail_from_buf(buf)
        if code == 0:
            update_job(job_id, status="done", message="Video generado.", log_tail=tail)
            if upload_dir:
                shutil.rmtree(upload_dir, ignore_errors=True)
        else:
            update_job(
                job_id,
                status="error",
                message=f"El proceso terminó con código {code}.",
                log_tail=tail,
            )
    except Exception as exc:  # noqa: BLE001
        update_job(
            job_id,
            status="error",
            message=str(exc),
            log_tail=_tail_from_buf(buf),
        )


def _queue_worker_loop() -> None:
    while True:
        job_id = _job_fifo.get()
        try:
            row = get_job(job_id)
            if row and row["status"] == "queued":
                _run_job_subprocess(job_id)
        finally:
            _job_fifo.task_done()


def _ensure_worker_thread() -> None:
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    threading.Thread(target=_queue_worker_loop, daemon=True).start()


def _enqueue(job_id: str) -> None:
    _job_fifo.put(job_id)
    _ensure_worker_thread()


def _prepare_sources_multipart(job_dir: Path | None) -> tuple[Path | None, str | None]:
    """Devuelve (carpeta_imágenes, error)."""
    folder_txt = (request.form.get("image_folder") or "").strip()
    archive = request.files.get("archive")
    images = request.files.getlist("images")

    has_zip = bool(archive and archive.filename)
    has_files = any(getattr(f, "filename", None) for f in images)

    if has_zip and has_files:
        return None, "Envía solo un ZIP o solo archivos de carpeta, no ambos."

    if (has_zip or has_files) and job_dir is None:
        return None, "Error interno: falta carpeta temporal."

    dest_img = (job_dir / "images") if job_dir else Path()
    if has_zip:
        raw_name = secure_filename(archive.filename or "upload.zip") or "upload.zip"
        zip_path = job_dir / raw_name
        archive.save(zip_path)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extract_zip(zf, dest_img)
        except (zipfile.BadZipFile, ValueError) as e:
            return None, str(e)
        zip_path.unlink(missing_ok=True)
        return dest_img, None

    if has_files:
        n = _save_flat_images(images, dest_img)
        if n == 0:
            return None, "No se subieron imágenes válidas (jpg, png, webp…)."
        return dest_img, None

    if folder_txt:
        try:
            return _validate_folder(folder_txt), None
        except ValueError as e:
            return None, str(e)

    return None, "Indica una carpeta local o sube imágenes / un ZIP."


def _resolve_audio_multipart(job_dir: Path | None) -> tuple[Path | None, float | None, str | None]:
    """(audio_path_abs | None, duration_if_no_audio, error)."""
    audio_path_txt = (request.form.get("audio_path") or "").strip()
    audio_file = request.files.get("audio_file")

    if audio_file and audio_file.filename:
        if job_dir is None:
            return None, None, "Error interno al guardar audio."
        raw = secure_filename(audio_file.filename) or "audio.bin"
        dest = job_dir / raw
        audio_file.save(dest)
        return dest.resolve(), None, None

    if audio_path_txt:
        try:
            return _validate_audio(audio_path_txt), None, None
        except ValueError as e:
            return None, None, str(e)

    dur_raw = (request.form.get("duration") or "").strip()
    if not dur_raw:
        return None, None, "Indica duración en segundos, ruta de audio o archivo de audio."
    try:
        d = float(dur_raw)
    except ValueError:
        return None, None, "Duración inválida."
    if d <= 0:
        return None, None, "La duración debe ser mayor que 0."
    return None, d, None


def _parse_common_fields(form: Any) -> tuple[str, int, int, int, int, float]:
    filter_mode = (form.get("filter") or "all").strip().lower()
    if filter_mode not in ("all", "even", "odd"):
        raise ValueError("Filtro inválido (usa all, even u odd).")
    width = int(form.get("width") or 1920)
    height = int(form.get("height") or 1080)
    fps = int(form.get("fps") or 30)
    seed = int(form.get("seed") or 42)
    intensity = float(form.get("intensity") or 0.04)
    if not (1 <= fps <= 120):
        raise ValueError("FPS debe estar entre 1 y 120.")
    intensity = max(0.01, min(0.15, intensity))
    return filter_mode, width, height, fps, seed, intensity


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/presets", methods=["GET"])
def api_presets() -> tuple[Response, int]:
    presets = load_yaml_presets_merged()
    defaults = {}
    if YAML_REPO.is_file():
        try:
            with open(YAML_REPO, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            defaults = data.get("defaults") or {}
        except OSError:
            pass
    out: dict[str, Any] = {}
    for name, p in presets.items():
        if not isinstance(p, dict):
            continue
        out[name] = {
            "description": p.get("description", ""),
            "width": p.get("width"),
            "height": p.get("height"),
            "fps": p.get("fps"),
            "intensity": p.get("intensity"),
        }
    return jsonify(presets=out, defaults=defaults), 200


@app.route("/api/jobs", methods=["GET"])
def api_jobs_list() -> tuple[Response, int]:
    lim = request.args.get("limit", "25")
    try:
        n = min(max(int(lim), 1), 100)
    except ValueError:
        n = 25
    jobs = list_jobs(n)
    for j in jobs:
        j["download"] = f"/download/{j['job_id']}" if j["status"] == "done" else None
    return jsonify(jobs=jobs), 200


@app.route("/api/jobs", methods=["POST"])
def create_job() -> tuple[Response, int]:
    if not SCRIPT.is_file():
        return jsonify(error="No se encontró gallery_to_video.py en el repositorio."), 500

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if request.content_type and "multipart/form-data" in request.content_type:
        return _create_job_multipart()

    try:
        payload = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify(error="JSON inválido."), 400

    image_folder = (payload.get("image_folder") or "").strip()
    audio_raw = (payload.get("audio_path") or "").strip()
    duration = payload.get("duration")
    filter_mode = (payload.get("filter") or "all").strip().lower()

    try:
        folder = _validate_folder(image_folder)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    audio_path: Path | None = None
    duration_f: float | None = None
    if audio_raw:
        try:
            audio_path = _validate_audio(audio_raw)
        except ValueError as e:
            return jsonify(error=str(e)), 400
    else:
        if duration is None:
            return jsonify(error="Indica duración en segundos o una ruta de audio."), 400
        try:
            duration_f = float(duration)
        except (TypeError, ValueError):
            return jsonify(error="Duración inválida."), 400
        if duration_f <= 0:
            return jsonify(error="La duración debe ser mayor que 0."), 400

    if filter_mode not in ("all", "even", "odd"):
        return jsonify(error="Filtro inválido (usa all, even u odd)."), 400

    try:
        width = int(payload.get("width", 1920))
        height = int(payload.get("height", 1080))
        fps = int(payload.get("fps", 30))
        seed = int(payload.get("seed", 42))
        intensity = float(payload.get("intensity", 0.04))
    except (TypeError, ValueError):
        return jsonify(error="Parámetros numéricos inválidos."), 400

    if not (1 <= fps <= 120):
        return jsonify(error="FPS debe estar entre 1 y 120."), 400

    intensity = max(0.01, min(0.15, intensity))

    out_name = f"ken_burns_{uuid.uuid4().hex[:12]}.mp4"
    output_path = OUTPUT_DIR / out_name

    cmd = _build_cmd(
        folder,
        output_path,
        audio_path=audio_path,
        duration_f=duration_f,
        filter_mode=filter_mode,
        width=width,
        height=height,
        fps=fps,
        intensity=intensity,
        seed=seed,
    )

    job_id = uuid.uuid4().hex
    insert_job(job_id, cmd, str(output_path), out_name, upload_dir=None)
    _enqueue(job_id)
    return jsonify(job_id=job_id), 202


def _create_job_multipart() -> tuple[Response, int]:
    job_id = uuid.uuid4().hex
    archive = request.files.get("archive")
    images = request.files.getlist("images")
    audio_file = request.files.get("audio_file")
    has_zip = bool(archive and archive.filename)
    has_files = any(getattr(f, "filename", None) for f in images)
    needs_staging = has_zip or has_files or bool(audio_file and audio_file.filename)

    job_dir: Path | None = (UPLOAD_ROOT / job_id) if needs_staging else None
    if job_dir is not None:
        job_dir.mkdir(parents=True, exist_ok=True)

    folder, err = _prepare_sources_multipart(job_dir)
    if err:
        if job_dir is not None:
            shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify(error=err), 400

    audio_path, duration_f, err = _resolve_audio_multipart(job_dir)
    if err:
        if job_dir is not None:
            shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify(error=err), 400

    try:
        filter_mode, width, height, fps, seed, intensity = _parse_common_fields(request.form)
    except (ValueError, TypeError) as e:
        if job_dir is not None:
            shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify(error=str(e)), 400

    assert folder is not None

    out_name = f"ken_burns_{uuid.uuid4().hex[:12]}.mp4"
    output_path = OUTPUT_DIR / out_name

    cmd = _build_cmd(
        folder,
        output_path,
        audio_path=audio_path,
        duration_f=duration_f,
        filter_mode=filter_mode,
        width=width,
        height=height,
        fps=fps,
        intensity=intensity,
        seed=seed,
    )

    upload_stored = str(job_dir.resolve()) if job_dir is not None else None

    insert_job(job_id, cmd, str(output_path), out_name, upload_dir=upload_stored)
    _enqueue(job_id)
    return jsonify(job_id=job_id), 202


@app.route("/api/jobs/<job_id>", methods=["GET"])
def job_status(job_id: str) -> tuple[Response, int]:
    job = get_job(job_id)
    if not job:
        return jsonify(error="Job no encontrado."), 404
    body = {
        "status": job["status"],
        "message": job["message"],
        "log_tail": job["log_tail"] or "",
    }
    if job["status"] == "done":
        body["download"] = f"/download/{job_id}"
    return jsonify(body), 200


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id: str) -> Response:
    job = get_job(job_id)
    if not job or job["status"] != "done":
        return jsonify(error="Video no disponible."), 404
    path = Path(job["output_path"])
    if not path.is_file():
        return jsonify(error="Archivo de salida ausente."), 404
    return send_file(path, as_attachment=True, download_name=job["download_name"])


def init_web_app() -> None:
    init_db()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    for jid in recover_after_restart():
        _enqueue(jid)


init_web_app()


@app.errorhandler(413)
def handle_too_large(_e: Any) -> tuple[Response, int]:
    return jsonify(error="Archivo demasiado grande (máx. ~512 MB por petición)."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, threaded=True, debug=False)
