"""Filesystem layout of a project checkout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def data_raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def data_derived(self) -> Path:
        return self.root / "data" / "derived"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def manifest(self) -> Path:
        return self.root / "data" / "manifest.json"

    @classmethod
    def from_cwd(cls) -> ProjectPaths:
        return cls(Path.cwd())
