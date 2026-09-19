from pathlib import Path

import pytest

from gb2035.data.fleet import build_fleet_by_zone
from gb2035.data.zones import load_zones


@pytest.fixture(scope="module")
def zones(repo_root: Path):
    return load_zones(repo_root / "data" / "derived" / "zones.geojson")


def test_fixture_fleet(fixtures_dir: Path, repo_root: Path, zones):
    fleet = build_fleet_by_zone(
        fixtures_dir / "power_stations_sample.csv",
        repo_root / "config" / "committed_plants.csv",
        zones,
    )
    by = fleet.set_index(["technology", "zone"])["p_nom_mw"]
    assert by[("ccgt", "Z9")] == 1380.0
    assert by[("ccgt", "Z8")] == 735.0
    assert by[("ocgt", "Z11")] == 350.0 or by[("ocgt", "Z10")] == 350.0
    assert "coal" not in set(fleet["technology"])
    assert by.xs("nuclear")["Z12"] == 1198.0, "Sizewell B is committed; existing AGRs are excluded"
    assert by.xs("nuclear").sum() == 3260.0 + 1198.0
    assert set(fleet.columns) == {"zone", "technology", "p_nom_mw"}


@pytest.mark.slow
def test_real_fleet_totals(repo_root: Path, zones):
    raw = repo_root / "data" / "raw" / "power_stations_locations.csv"
    if not raw.exists():
        pytest.skip("run gb2035 retrieve first")
    fleet = build_fleet_by_zone(raw, repo_root / "config" / "committed_plants.csv", zones)
    totals = fleet.groupby("technology")["p_nom_mw"].sum()
    assert 25_000 < totals["ccgt"] < 30_000
    assert 1_000 < totals["ocgt"] < 2_500
    assert totals["nuclear"] == 3260.0 + 1198.0
