"""Image record persistence helpers.

Phase 1/2 image architecture:
- Track generated/static image metadata in a first-class images table.
- Keep legacy filename fields in stories/characters for backward compatibility.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path


def _guess_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    return "application/octet-stream"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def create_image_record(
    conn: sqlite3.Connection,
    *,
    kind: str,
    scope: str,
    owner_type: str | None,
    owner_id: int | None,
    owner_key: str | None,
    prompt: str,
    negative_prompt: str = "",
    seed: int | None = None,
    workflow_name: str = "FluxForRPG",
    model_name: str = "",
    width: int | None = None,
    height: int | None = None,
    provider: str = "comfyui",
) -> int:
    cur = conn.execute(
        """INSERT INTO images (
               kind, scope, owner_type, owner_id, owner_key, status,
               prompt, negative_prompt, seed, workflow_name, model_name,
               width, height, provider
           ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            kind,
            scope,
            owner_type,
            owner_id,
            owner_key,
            prompt,
            negative_prompt,
            seed,
            workflow_name,
            model_name,
            width,
            height,
            provider,
        ),
    )
    return int(cur.lastrowid)


def mark_image_ready(conn: sqlite3.Connection, image_id: int, storage_path: str) -> None:
    mime = _guess_mime(storage_path)
    digest = sha256_file(storage_path) if os.path.exists(storage_path) else ""
    conn.execute(
        """UPDATE images
           SET status = 'ready',
               storage_path = ?,
               mime = ?,
               sha256 = ?,
               error = '',
               updated_at = datetime('now')
           WHERE id = ?""",
        (storage_path, mime, digest, image_id),
    )


def mark_image_failed(conn: sqlite3.Connection, image_id: int, error: str) -> None:
    conn.execute(
        """UPDATE images
           SET status = 'failed',
               error = ?,
               updated_at = datetime('now')
           WHERE id = ?""",
        (error[:1000], image_id),
    )

