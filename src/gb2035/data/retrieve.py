"""Download manifest entries into data/raw and verify their checksums."""

from __future__ import annotations

import shutil
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gb2035.data.manifest import ManifestEntry, md5_of, sha256_of

USER_AGENT = "gb2035/0.1 (+https://github.com/younis-y/gb-2035-pypsa)"


class RetrieveError(RuntimeError):
    """A manifest entry could not be fetched or verified."""


class ChecksumError(RetrieveError):
    """The file on disk does not match the manifest checksum."""


@dataclass(frozen=True)
class RetrieveReport:
    name: str
    path: Path
    action: Literal["downloaded", "verified", "pinned"]
    sha256: str
    size_bytes: int


def download_to(url: str, dest: Path) -> None:
    """Stream `url` to `dest`, writing to a temporary file first."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    tmp.replace(dest)


def _verify(entry: ManifestEntry, path: Path) -> str:
    digest = sha256_of(path)
    if entry.sha256 is not None and digest != entry.sha256:
        msg = f"{path.name}: sha256 {digest} does not match manifest {entry.sha256}"
        raise ChecksumError(msg)
    if entry.sha256 is None and entry.md5 is not None and md5_of(path) != entry.md5:
        msg = f"{path.name}: md5 does not match manifest {entry.md5}"
        raise ChecksumError(msg)
    return digest


def retrieve(
    entries: dict[str, ManifestEntry],
    raw_dir: Path,
    only: Iterable[str] | None = None,
    pin: bool = False,
    fetch: Callable[[str, Path], None] = download_to,
) -> list[RetrieveReport]:
    """Ensure every selected entry exists in `raw_dir` with a matching checksum.

    With `pin=True`, entries lacking a sha256 are downloaded and their digest returned so the
    caller can write it back to the manifest. Without it, such entries are an error.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    selected = list(only) if only is not None else list(entries)
    reports: list[RetrieveReport] = []
    for name in selected:
        entry = entries[name]
        path = raw_dir / entry.filename
        if entry.sha256 is None and entry.md5 is None and not pin:
            msg = f"{name} has no checksum; run retrieve with --pin to record one"
            raise RetrieveError(msg)
        if path.exists():
            if entry.sha256 is None and pin:
                digest = _verify(entry, path)
                action: Literal["downloaded", "verified", "pinned"] = "pinned"
            else:
                digest = _verify(entry, path)
                action = "verified"
        else:
            try:
                fetch(entry.url, path)
            except OSError as exc:
                msg = f"{name}: download failed from {entry.url}: {exc}"
                raise RetrieveError(msg) from exc
            if entry.sha256 is None and pin:
                digest = _verify(entry, path)
                action = "pinned"
            else:
                digest = _verify(entry, path)
                action = "downloaded"
        reports.append(RetrieveReport(name, path, action, digest, path.stat().st_size))
    return reports
