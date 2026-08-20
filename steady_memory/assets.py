"""Safe asset ingestion without making media a canonical text source."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from .archive import ArchiveStore, ValidationError


CATEGORIES = {"progress", "exercise", "journal", "other"}
DEFAULT_MEDIA_ROOT = "media"


def media_root(store: ArchiveStore) -> Path:
    """Return the vault-local media directory without allowing path escape."""
    try:
        manifest = json.loads(store.paths.manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid steady.json: {exc}") from exc
    configured = manifest.get("media_root") or DEFAULT_MEDIA_ROOT
    if not isinstance(configured, str) or not configured.strip():
        raise ValidationError("media_root must be a non-empty relative path")
    relative = Path(configured)
    if relative.is_absolute():
        raise ValidationError("media_root must stay inside the vault")
    target = (store.paths.root / relative).resolve()
    try:
        target.relative_to(store.paths.root)
    except ValueError as exc:
        raise ValidationError("media_root must stay inside the vault") from exc
    if target == store.paths.root:
        raise ValidationError("media_root cannot be the vault root")
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def indexed_media(store: ArchiveStore) -> tuple[list[Path], list[str]]:
    """Resolve indexed media paths and report unsafe or missing entries."""
    _, rows = store.read_csv(store.paths.assets_csv)
    files: list[Path] = []
    errors: list[str] = []
    for row in rows:
        value = row.get("original_relpath", "")
        candidate = (store.paths.root / value).resolve()
        try:
            candidate.relative_to(store.paths.root)
        except ValueError:
            errors.append(f"asset path escapes vault: {value}")
            continue
        if not candidate.is_file():
            errors.append(f"missing asset: {value}")
            continue
        files.append(candidate)
    return files, errors


def record_asset(store: ArchiveStore, *, source_path: str, day: date, category: str,
                 note: str = "") -> dict[str, Any]:
    source = Path(source_path).resolve()
    if not source.is_file(): raise ValidationError("source_path must be an existing file")
    if category not in CATEGORIES: raise ValidationError(f"category must be one of: {', '.join(sorted(CATEGORIES))}")
    if source.stat().st_size > 100 * 1024 * 1024: raise ValidationError("asset exceeds 100 MiB")
    raw_hash = _sha256(source)
    fields, rows = store.read_csv(store.paths.assets_csv)
    existing = next((row for row in rows if row.get("sha256") == raw_hash), None)
    if existing:
        existing_path = (store.paths.root / existing.get("original_relpath", "")).resolve()
        try:
            existing_path.relative_to(store.paths.root)
        except ValueError as exc:
            raise ValidationError("indexed asset path escapes vault") from exc
        if existing_path.is_file():
            return {"changed_files": [], "asset_id": existing["asset_id"], "sha256": raw_hash, "duplicate": True}
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, existing_path)
        return {"changed_files": [store.relative(existing_path)], "asset_id": existing["asset_id"],
                "sha256": raw_hash, "restored": True, "media_backed_up": False}
    asset_id = uuid.uuid4().hex
    suffix = source.suffix.lower() or ".bin"
    target = media_root(store) / category / f"{day:%Y}" / f"{day:%m}" / f"{day.isoformat()}-{asset_id[:8]}{suffix}"
    relative = target.relative_to(store.paths.root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        shutil.copy2(source, temp)
        os.replace(temp, target)
        rows.append({"asset_id": asset_id, "date": day.isoformat(), "category": category, "sha256": raw_hash,
                     "original_relpath": relative.as_posix(), "preview_relpath": "", "original_bytes": source.stat().st_size,
                     "preview_bytes": "", "width": "", "height": "", "note": note.strip()})
        try:
            store.atomic_write_many({store.paths.assets_csv: store.csv_text(fields, rows)})
        except Exception:
            target.unlink(missing_ok=True)
            raise
    finally:
        temp.unlink(missing_ok=True)
    return {"changed_files": [store.relative(target), store.relative(store.paths.assets_csv)], "asset_id": asset_id,
            "sha256": raw_hash, "media_backed_up": False}
