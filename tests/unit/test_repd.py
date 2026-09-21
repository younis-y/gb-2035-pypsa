from pathlib import Path

import pytest

from gb2035.data.repd import build_repd_by_zone
from gb2035.data.zones import load_zones


@pytest.fixture(scope="module")
def zones(repo_root: Path):
    return load_zones(repo_root / "data" / "derived" / "zones.geojson")


def test_fixture_repd(fixtures_dir: Path, zones):
    out = build_repd_by_zone(fixtures_dir / "repd_sample.csv", zones)
    key = out.set_index(["technology", "status", "zone"])["p_nom_mw"]
    assert key[("onwind", "operational", "Z5")] == 539.0
    assert key[("offwind", "operational", "Z8")] == 1386.0, "Hornsea Two lands at Z8"
    assert key[("solar", "under_construction", "Z15")] == 373.0
    assert key[("pumped_hydro", "operational", "Z9")] == 1728.0
    assert "battery" not in set(out["technology"]), "Northern Ireland is excluded"
    assert out["p_nom_mw"].sum() == 539.0 + 1386.0 + 373.0 + 1728.0, (
        "refused and unparseable rows dropped"
    )
    assert set(out.columns) == {"zone", "technology", "status", "p_nom_mw"}


def test_offshore_site_inside_named_polygon_lands_at_mapped_zone(tmp_path: Path, zones):
    from pyproj import Transformer

    from gb2035.data.zones import OFFSHORE_LANDING

    point = zones.loc["HORNSEA", "geometry"].representative_point()
    to_osgb = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    x, y = to_osgb.transform(point.x, point.y)
    csv = tmp_path / "repd.csv"
    csv.write_text(
        "Ref ID,Site Name,Technology Type,Installed Capacity (MWelec),Development Status (short),Country,X-coordinate,Y-coordinate\n"
        f"1,Inside Hornsea,Wind Offshore,1000,Operational,England,{x:.0f},{y:.0f}\n",
        encoding="latin-1",
    )
    out = build_repd_by_zone(csv, zones)
    assert out.loc[0, "zone"] == OFFSHORE_LANDING["HORNSEA"] == "Z8"


@pytest.mark.slow
def test_real_repd_totals(repo_root: Path, zones):
    raw = repo_root / "data" / "raw" / "REPD_Publication_Q2_2026.csv"
    if not raw.exists():
        pytest.skip("run gb2035 retrieve first")
    out = build_repd_by_zone(raw, zones)
    gw = out.groupby(["technology", "status"])["p_nom_mw"].sum() / 1e3
    assert 13 < gw[("onwind", "operational")] < 16
    assert 14 < gw[("offwind", "operational")] < 18
    assert 9 < gw[("solar", "operational")] < 13
    assert 2.5 < gw[("pumped_hydro", "operational")] < 3.2
    assert set(out["zone"]) <= set(zones[zones["kind"] == "land"].index)
