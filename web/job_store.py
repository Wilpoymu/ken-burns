"""Persistencia de jobs (SQLite) para la UI web Ken Burns."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "data" / "jobs.sqlite"

_db_lock = None  # lazy threading.Lock


def _lock():
    global _db_lock
    if _db_lock is None:
        import threading

        _db_lock = threading.Lock()
    return _db_lock


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock():
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    message TEXT,
                    output_path TEXT,
                    download_name TEXT,
                    log_tail TEXT,
                    cmd_json TEXT NOT NULL,
                    upload_dir TEXT,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def insert_job(
    job_id: str,
    cmd: list[str],
    output_path: str,
    download_name: str,
    upload_dir: str | None,
    status: str = "queued",
    message: str = "En cola…",
) -> None:
    now = time.time()
    with _lock():
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, message, output_path, download_name,
                    log_tail, cmd_json, upload_dir, created_ts, updated_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    status,
                    message,
                    output_path,
                    download_name,
                    "",
                    json.dumps(cmd),
                    upload_dir,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_ts"] = time.time()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values())
    vals.append(job_id)
    with _lock():
        conn = _connect()
        try:
            conn.execute(f"UPDATE jobs SET {cols} WHERE job_id = ?", vals)
            conn.commit()
        finally:
            conn.close()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock():
        conn = _connect()
        try:
            cur = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_jobs(limit: int = 25) -> list[dict[str, Any]]:
    with _lock():
        conn = _connect()
        try:
            cur = conn.execute(
                "SELECT job_id, status, message, download_name, created_ts, updated_ts "
                "FROM jobs ORDER BY created_ts DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def recover_after_restart() -> list[str]:
    """Marca ejecuciones cortadas y devuelve job_ids aún en cola."""
    now = time.time()
    with _lock():
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE jobs SET status = 'interrupted', message = ?,
                    updated_ts = ? WHERE status = 'running'
                """,
                ("El servidor se reinició durante el render.", now),
            )
            cur = conn.execute(
                "SELECT job_id FROM jobs WHERE status = 'queued' ORDER BY created_ts ASC"
            )
            queued = [r[0] for r in cur.fetchall()]
            conn.commit()
            return queued
        finally:
            conn.close()
