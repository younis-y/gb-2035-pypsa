"""Pinned external inputs with checksums."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    filename: str
    licence: str
    source_note: str = ""
    sha256: str | None = None
    md5: str | None = None
    size_bytes: int | None = None


def _digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of(path: Path) -> str:
    return _digest(path, "sha256")


def md5_of(path: Path) -> str:
    return _digest(path, "md5")


def load_manifest(path: Path) -> dict[str, ManifestEntry]:
    raw = json.loads(path.read_text())
    return {
        name: ManifestEntry.model_validate({"name": name, **body}) for name, body in raw.items()
    }


def save_manifest(path: Path, entries: dict[str, ManifestEntry]) -> None:
    body = {name: e.model_dump(exclude={"name"}) for name, e in entries.items()}
    path.write_text(json.dumps(body, indent=2) + "\n")
