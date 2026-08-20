"""Filesystem primitives for a portable Steady Memory archive."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_VERSION = 1
MANIFEST = "steady.json"


class ArchiveError(Exception):
    def __init__(self, message: str, code: str = "archive_error") -> None:
        super().__init__(message)
        self.code = code


class ValidationError(ArchiveError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "validation_error")


class ConflictError(ArchiveError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "conflict")


class PermissionDenied(ArchiveError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "permission_denied")


def parse_date(value: str | None, *, default_today: bool = False) -> date:
    if not value and default_today:
        return date.today()
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError("date must use YYYY-MM-DD") from exc


def number(value: Any, name: str, *, minimum: float | None = None,
           maximum: float | None = None, required: bool = False) -> float | None:
    if value in (None, ""):
        if required:
            raise ValidationError(f"{name} is required")
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a number") from exc
    if not math.isfinite(result):
        raise ValidationError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValidationError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValidationError(f"{name} must be <= {maximum}")
    return result


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class ArchivePaths:
    root: Path

    @classmethod
    def discover(cls, root: str | os.PathLike[str] | None = None) -> "ArchivePaths":
        configured = root or os.environ.get("STEADY_ROOT")
        candidate = Path(configured or Path.cwd()).resolve()
        if not configured and not (candidate / MANIFEST).is_file() and (candidate / "vault" / MANIFEST).is_file():
            candidate = candidate / "vault"
        manifest = candidate / MANIFEST
        if not manifest.is_file():
            raise ValidationError(f"{candidate} is not initialized; run `python -m steady_memory setup`")
        return cls(candidate)

    @property
    def runtime(self) -> Path: return self.root / ".steady"
    @property
    def manifest(self) -> Path: return self.root / MANIFEST
    @property
    def weight_csv(self) -> Path: return self.root / "data" / "weight.csv"
    @property
    def body_metrics_csv(self) -> Path: return self.root / "data" / "body_metrics.csv"
    @property
    def exercise_csv(self) -> Path: return self.root / "data" / "exercise.csv"
    @property
    def profile_json(self) -> Path: return self.root / "data" / "profile.json"
    @property
    def assets_csv(self) -> Path: return self.root / "data" / "assets.csv"

    def daily_record(self, day: date) -> Path:
        return self.root / "records" / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.md"


class ArchiveStore:
    def __init__(self, paths: ArchivePaths) -> None:
        self.paths = paths

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.paths.runtime.mkdir(parents=True, exist_ok=True)
        handle = (self.paths.runtime / "archive.lock").open("a+b")
        try:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0"); handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.paths.root).as_posix()

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_csv(self, path: Path) -> tuple[list[str], list[dict[str, str]]]:
        if not path.is_file():
            raise ValidationError(f"missing file: {self.relative(path)}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), [dict(row) for row in reader]

    def csv_text(self, fields: list[str], rows: Iterable[dict[str, Any]]) -> str:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        return output.getvalue()

    def atomic_write_many(self, changes: dict[Path, str]) -> list[str]:
        prepared: dict[Path, Path] = {}
        originals: dict[Path, bytes | None] = {}
        replaced: list[Path] = []
        try:
            for path, content in changes.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                originals[path] = path.read_bytes() if path.exists() else None
                fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
                temp = Path(name)
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                    handle.write(content); handle.flush(); os.fsync(handle.fileno())
                prepared[path] = temp
            for path, temp in prepared.items():
                os.replace(temp, path); replaced.append(path)
            return [self.relative(path) for path in changes]
        except Exception:
            for path in reversed(replaced):
                original = originals[path]
                if original is None: path.unlink(missing_ok=True)
                else: path.write_bytes(original)
            raise
        finally:
            for temp in prepared.values(): temp.unlink(missing_ok=True)

    def append_audit(self, tool: str, success: bool, changed_files: list[str] | None = None,
                     request_id: str | None = None, error_code: str | None = None) -> None:
        self.paths.runtime.mkdir(parents=True, exist_ok=True)
        entry: dict[str, Any] = {"at": datetime.now().astimezone().isoformat(), "tool": tool,
                                 "success": success, "changed_files": changed_files or []}
        if request_id: entry["request_id"] = request_id
        if error_code: entry["error_code"] = error_code
        with (self.paths.runtime / "audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def canonical_files(self) -> list[Path]:
        candidates = [self.paths.manifest, self.paths.root / "memory.md"]
        candidates += sorted((self.paths.root / "memory").glob("*.md"))
        candidates += sorted((self.paths.root / "plans").glob("*.json"))
        candidates += sorted((self.paths.root / "records").glob("**/*.md"))
        candidates += sorted((self.paths.root / "data").glob("*.csv"))
        candidates += sorted((self.paths.root / "data").glob("*.json"))
        return [path for path in candidates if path.is_file()]

    def backup_files(self) -> list[Path]:
        candidates = self.canonical_files() + [self.paths.root / "AGENTS.md", self.paths.root / ".gitignore"]
        return list(dict.fromkeys(path for path in candidates if path.is_file()))
