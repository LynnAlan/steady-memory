"""Portable, verifiable ZIP backups."""

from __future__ import annotations

import hashlib
import json
import zipfile
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .archive import ArchiveStore, ConflictError, ValidationError


def backup_archive(store: ArchiveStore, output_path: str, *, replace: bool = False) -> dict[str, Any]:
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
            for path in store.canonical_files():
                relative = store.relative(path)
                raw = path.read_bytes()
                archive.writestr(f"archive/{relative}", raw)
                entries.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)})
            manifest = {"format": "steady-memory-backup-v1", "created_at": datetime.now(timezone.utc).isoformat(), "files": entries}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return {"backup": str(output), "files": len(entries), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def verify_backup(backup_path: str) -> dict[str, Any]:
    path = Path(backup_path).resolve()
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for entry in manifest.get("files", []):
                raw = archive.read(f"archive/{entry['path']}")
                if len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    errors.append(entry["path"])
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors, "backup": str(path)}
