"""Safe asset ingestion without making media a canonical text source."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from .archive import ArchiveStore, ValidationError


CATEGORIES = {"progress", "exercise", "journal", "other"}


def record_asset(store: ArchiveStore, *, source_path: str, day: date, category: str,
                 note: str = "") -> dict[str, Any]:
    source = Path(source_path).resolve()
    if not source.is_file(): raise ValidationError("source_path must be an existing file")
    if category not in CATEGORIES: raise ValidationError(f"category must be one of: {', '.join(sorted(CATEGORIES))}")
    if source.stat().st_size > 100 * 1024 * 1024: raise ValidationError("asset exceeds 100 MiB")
    raw_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    fields, rows = store.read_csv(store.paths.assets_csv)
    existing = next((row for row in rows if row.get("sha256") == raw_hash), None)
    if existing:
        return {"changed_files": [], "asset_id": existing["asset_id"], "sha256": raw_hash, "duplicate": True}
    asset_id = uuid.uuid4().hex
    suffix = source.suffix.lower() or ".bin"
    relative = Path("assets") / category / f"{day:%Y}" / f"{day:%m}" / f"{day.isoformat()}-{asset_id[:8]}{suffix}"
    target = store.paths.root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    rows.append({"asset_id": asset_id, "date": day.isoformat(), "category": category, "sha256": raw_hash,
                 "original_relpath": relative.as_posix(), "preview_relpath": "", "original_bytes": source.stat().st_size,
                 "preview_bytes": "", "width": "", "height": "", "note": note.strip()})
    store.atomic_write_many({store.paths.assets_csv: store.csv_text(fields, rows)})
    return {"changed_files": [store.relative(target), store.relative(store.paths.assets_csv)], "asset_id": asset_id,
            "sha256": raw_hash}
