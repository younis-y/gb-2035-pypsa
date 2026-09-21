import json
from pathlib import Path

from gb2035.data.manifest import ManifestEntry, load_manifest, save_manifest, sha256_of


def test_sha256_of_known_bytes(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"abc")
    assert sha256_of(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_manifest_roundtrip(tmp_path: Path):
    entries = {
        "a": ManifestEntry(
            name="a", url="https://example.org/a.csv", filename="a.csv", licence="MIT"
        ),
    }
    path = tmp_path / "manifest.json"
    save_manifest(path, entries)
    loaded = load_manifest(path)
    assert loaded["a"].url == "https://example.org/a.csv"
    assert loaded["a"].sha256 is None
    assert json.loads(path.read_text())["a"]["filename"] == "a.csv"


def test_repo_manifest_is_complete(repo_root: Path):
    entries = load_manifest(repo_root / "data" / "manifest.json")
    required = {
        "pypsa_gb_buses",
        "pypsa_gb_links",
        "pypsa_gb_links_future",
        "pypsa_gb_zone_definitions",
        "pypsa_gb_zones_geojson",
        "pypsa_gb_transmission_2030",
        "pypsa_gb_power_stations",
        "repd_q2_2026",
        "neso_demand_2019",
        "fes2025_workbook",
        "technology_data_costs_2035",
        "desnz_generation_costs_2025_annex_a",
        "zenodo_cutout_uk_2019",
    }
    assert required <= set(entries)
    for e in entries.values():
        assert e.licence, e.name
        assert e.sha256 or e.md5, f"{e.name} needs a checksum"
