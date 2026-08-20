"""Portable, verifiable ZIP backups."""

from __future__ import annotations

import hashlib
import json
import zipfile
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .archive import ArchiveStore, ConflictError, ValidationError
from .assets import indexed_media

BACKUP_FORMAT = "steady-memory-backup-v1"
MAX_BACKUP_FILES = 100_000
MAX_RESTORE_BYTES = 100 * 1024 * 1024 * 1024


def _safe_relative(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValidationError("backup contains an invalid path")
    path = Path(value)
    if path.is_absolute() or path.drive or ".." in path.parts or path.as_posix() != value or any(":" in part for part in path.parts):
        raise ValidationError(f"backup contains an unsafe path: {value}")
    return path


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"invalid backup manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
        raise ValidationError("unsupported backup format")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValidationError("backup manifest files must be a list")
    if len(entries) > MAX_BACKUP_FILES:
        raise ValidationError(f"backup contains too many files; maximum is {MAX_BACKUP_FILES}")
    seen: set[str] = set()
    total_size = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValidationError("backup manifest contains an invalid file entry")
        relative = _safe_relative(entry.get("path"))
        value = relative.as_posix()
        if value in seen:
            raise ValidationError(f"backup contains a duplicate path: {value}")
        seen.add(value)
        if not isinstance(entry.get("size"), int) or entry["size"] < 0:
            raise ValidationError(f"backup contains an invalid size: {value}")
        total_size += entry["size"]
        if total_size > MAX_RESTORE_BYTES:
            raise ValidationError("backup expands beyond the 100 GiB safety limit")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValidationError(f"backup contains an invalid hash: {value}")
        try:
            info = archive.getinfo(f"archive/{value}")
        except KeyError as exc:
            raise ValidationError(f"backup is missing: {value}") from exc
        if info.file_size != entry["size"]:
            raise ValidationError(f"backup size mismatch: {value}")
    return manifest


def _entry_hash(archive: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_archive(store: ArchiveStore, output_path: str, *, replace: bool = False,
                   include_media: bool = False) -> dict[str, Any]:
    output = Path(output_path).resolve()
    if output.exists() and not replace: raise ConflictError(f"backup exists: {output}")
    if output.suffix.lower() != ".zip": raise ValidationError("backup output must end in .zip")
    try:
        output.relative_to(store.paths.root)
        raise ValidationError("backup output must be outside the vault")
    except ValueError:
        pass
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            paths = store.backup_files()
            if include_media:
                media, media_errors = indexed_media(store)
                if media_errors:
                    raise ValidationError("cannot include media: " + "; ".join(media_errors))
                paths += media
            for path in paths:
                relative = store.relative(path)
                size = path.stat().st_size
                archive.write(path, f"archive/{relative}")
                entries.append({"path": relative, "sha256": _file_hash(path), "size": size})
            manifest = {"format": BACKUP_FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                        "media_included": include_media, "files": entries}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return {"backup": str(output), "files": len(entries), "sha256": _file_hash(output),
            "media_included": include_media,
            "media_note": None if include_media else "Media is not included; use include_media=true for a complete backup."}


def verify_backup(backup_path: str) -> dict[str, Any]:
    path = Path(backup_path).resolve()
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = _read_manifest(archive)
            for entry in manifest["files"]:
                if _entry_hash(archive, f"archive/{entry['path']}") != entry["sha256"]:
                    errors.append(entry["path"])
    except (OSError, zipfile.BadZipFile, ValidationError) as exc:
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors, "backup": str(path)}


def restore_backup(backup_path: str, target_path: str) -> dict[str, Any]:
    """Restore a verified backup into a new directory without unsafe ZIP extraction."""
    backup = Path(backup_path).resolve()
    target = Path(target_path).resolve()
    if target.exists():
        raise ConflictError(f"restore target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=target.parent))
    restored = 0
    try:
        with zipfile.ZipFile(backup) as archive:
            manifest = _read_manifest(archive)
            for entry in manifest["files"]:
                relative = _safe_relative(entry["path"])
                name = f"archive/{relative.as_posix()}"
                if _entry_hash(archive, name) != entry["sha256"]:
                    raise ValidationError(f"backup hash mismatch: {relative.as_posix()}")
                output = stage / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, output.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                restored += 1
        if not (stage / "steady.json").is_file():
            raise ValidationError("backup does not contain steady.json")
        os.replace(stage, target)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"cannot restore backup: {exc}") from exc
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {"restored": True, "root": str(target), "files": restored,
            "media_included": bool(manifest.get("media_included", False))}
