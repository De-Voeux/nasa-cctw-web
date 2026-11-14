"""Append-only JSON-lines manifest: what was downloaded, its checksum, and whether it passed.

Lets a run resume: an item whose file still exists with the recorded SHA-256 is not fetched again.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.items: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.items[rec["key"]] = rec

    def record(self, key: str, **fields) -> dict:
        rec = {"key": key, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        self.items[key] = rec
        return rec

    def done(self, key: str) -> dict | None:
        rec = self.items.get(key)
        if not rec or rec.get("status") != "ok" or not rec.get("path"):
            return None
        p = Path(rec["path"])
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != rec.get("sha256"):
            return None
        return rec
