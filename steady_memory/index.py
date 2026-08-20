"""Rebuildable SQLite search index; canonical files remain the source of truth."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .archive import ArchiveStore, ValidationError


class SearchIndex:
    VERSION = "1"

    def __init__(self, store: ArchiveStore) -> None:
        self.store = store
        self.path = store.paths.runtime / "index.sqlite3"

    def _fingerprint(self) -> str:
        items = [(self.store.relative(path), hashlib.sha256(path.read_bytes()).hexdigest())
                 for path in self.store.canonical_files()]
        return hashlib.sha256(json.dumps(items, separators=(",", ":")).encode()).hexdigest()

    def is_current(self) -> bool:
        if not self.path.exists(): return False
        try:
            with closing(sqlite3.connect(self.path)) as db:
                meta = dict(db.execute("SELECT key,value FROM meta"))
            return meta.get("version") == self.VERSION and meta.get("fingerprint") == self._fingerprint()
        except sqlite3.Error:
            return False

    def rebuild(self) -> dict[str, Any]:
        documents: list[tuple[Any, ...]] = []
        for path in self.store.canonical_files():
            relative = self.store.relative(path)
            if path.suffix == ".csv":
                fields, rows = self.store.read_csv(path)
                for i, row in enumerate(rows, 2):
                    content = "; ".join(f"{key}: {row.get(key, '')}" for key in fields if row.get(key))
                    documents.append((relative, row.get("date", ""), f"row-{i-1}", content, i, i))
            else:
                text = self.store.read_text(path)
                if path.suffix == ".json":
                    try: json.loads(text)
                    except json.JSONDecodeError as exc: raise ValidationError(f"invalid JSON {relative}: {exc}") from exc
                chunks = re.split(r"(?m)(?=^##?\s+)", text)
                line = 1
                for chunk in chunks:
                    if not chunk.strip(): continue
                    title_match = re.match(r"^#{1,6}\s+(.+)", chunk)
                    title = title_match.group(1).strip() if title_match else path.stem
                    count = chunk.count("\n") + 1
                    date_match = re.search(r"\d{4}-\d{2}-\d{2}", path.name)
                    documents.append((relative, date_match.group(0) if date_match else "", title, chunk.strip(), line, line + count - 1))
                    line += count
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("DROP TABLE IF EXISTS documents; DROP TABLE IF EXISTS meta; CREATE TABLE documents(path TEXT,date TEXT,title TEXT,content TEXT,line_start INT,line_end INT); CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);")
            db.executemany("INSERT INTO documents VALUES(?,?,?,?,?,?)", documents)
            db.executemany("INSERT INTO meta VALUES(?,?)", [("version", self.VERSION), ("fingerprint", self._fingerprint())])
            db.commit()
        return {"documents": len(documents), "index": self.store.relative(self.path)}

    def search(self, query: str, *, limit: int = 10, date_from: str | None = None,
               date_to: str | None = None, path_prefix: str | None = None) -> list[dict[str, Any]]:
        query = str(query).strip()
        if not query: raise ValidationError("query is required")
        if not self.is_current(): self.rebuild()
        clauses, params = ["1=1"], []
        if date_from: clauses.append("date>=?"); params.append(date_from)
        if date_to: clauses.append("date<=?"); params.append(date_to)
        if path_prefix: clauses.append("path LIKE ?"); params.append(path_prefix.rstrip("/") + "%")
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute("SELECT * FROM documents WHERE " + " AND ".join(clauses), params)]
        needle = query.casefold()
        matched = [row for row in rows if needle in (row["title"] + "\n" + row["content"]).casefold()]
        matched.sort(key=lambda row: row["date"], reverse=True)
        return [{**row, "snippet": row.pop("content")[:320]} for row in matched[:max(1, min(int(limit), 50))]]
