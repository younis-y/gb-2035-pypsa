import hashlib
from pathlib import Path

import pytest

from gb2035.data.manifest import ManifestEntry
from gb2035.data.retrieve import ChecksumError, RetrieveError, retrieve

PAYLOAD = b"zone,x\nZ7,1\n"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def fake_fetch(url: str, dest: Path) -> None:
    dest.write_bytes(PAYLOAD)


def entry(sha: str | None = SHA) -> dict[str, ManifestEntry]:
    return {
        "e": ManifestEntry(
            name="e", url="https://x/e.csv", filename="e.csv", licence="MIT", sha256=sha
        )
    }


def test_downloads_and_verifies(tmp_path: Path):
    reports = retrieve(entry(), tmp_path, fetch=fake_fetch)
    assert reports[0].action == "downloaded"
    assert reports[0].sha256 == SHA
    assert (tmp_path / "e.csv").read_bytes() == PAYLOAD


def test_second_call_verifies_without_fetching(tmp_path: Path):
    retrieve(entry(), tmp_path, fetch=fake_fetch)

    def boom(url: str, dest: Path) -> None:
        raise AssertionError("must not fetch")

    reports = retrieve(entry(), tmp_path, fetch=boom)
    assert reports[0].action == "verified"


def test_checksum_mismatch_raises(tmp_path: Path):
    with pytest.raises(ChecksumError, match=r"e\.csv"):
        retrieve(entry(sha="0" * 64), tmp_path, fetch=fake_fetch)


def test_pin_fills_missing_checksum(tmp_path: Path):
    reports = retrieve(entry(sha=None), tmp_path, pin=True, fetch=fake_fetch)
    assert reports[0].action == "pinned"
    assert reports[0].sha256 == SHA


def test_missing_checksum_without_pin_raises(tmp_path: Path):
    with pytest.raises(RetrieveError, match="pin"):
        retrieve(entry(sha=None), tmp_path, fetch=fake_fetch)


def test_only_filter(tmp_path: Path):
    entries = entry() | {
        "other": ManifestEntry(
            name="other", url="https://x/o", filename="o.csv", licence="MIT", sha256=SHA
        )
    }
    reports = retrieve(entries, tmp_path, only=["other"], fetch=fake_fetch)
    assert [r.name for r in reports] == ["other"]
