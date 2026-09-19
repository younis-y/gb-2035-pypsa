from pathlib import Path

import pandas as pd
import pytest
from pyproj import Transformer

from gb2035.data.zones import (
    LAND_ZONES,
    OFFSHORE_LANDING,
    OFFSHORE_ZONES,
    assign_zone,
    load_zones,
    nearest_zone,
    zone_land_area_km2,
)


@pytest.fixture(scope="module")
def zones(repo_root: Path):
    return load_zones(repo_root / "data" / "derived" / "zones.geojson")


SITES = pd.DataFrame(
    {
        "name": ["Teesside", "Scunthorpe", "Port Talbot", "Grangemouth", "North Sea"],
        "lat": [54.60, 53.58, 51.59, 56.02, 56.5],
        "lon": [-1.15, -0.65, -3.78, -3.72, 3.0],
    }
)


def test_zone_sets(zones):
    assert len(LAND_ZONES) == 20 and len(OFFSHORE_ZONES) == 3
    assert set(zones.index) == set(LAND_ZONES) | set(OFFSHORE_ZONES)
    assert (zones.loc[list(OFFSHORE_ZONES), "kind"] == "offshore").all()
    assert set(OFFSHORE_LANDING.values()) <= set(LAND_ZONES)


def test_assign_zone_wgs84(zones):
    got = assign_zone(SITES, "lon", "lat", "EPSG:4326", zones)
    assert got.tolist()[:4] == ["Z7", "Z8", "Z13", "Z5"]
    assert pd.isna(got.iloc[4])


def test_assign_zone_osgb(zones):
    to_osgb = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    x, y = to_osgb.transform(SITES["lon"].to_numpy(), SITES["lat"].to_numpy())
    df = SITES.assign(x=x, y=y)
    got = assign_zone(df, "x", "y", "EPSG:27700", zones)
    assert got.tolist()[:4] == ["Z7", "Z8", "Z13", "Z5"]


def test_nearest_zone_for_offshore_point(zones):
    df = pd.DataFrame({"lon": [0.5], "lat": [54.0]})
    assert nearest_zone(df, "lon", "lat", "EPSG:4326", zones).iloc[0] in {"Z8", "Z12", "Z7"}


def test_nearest_zone_respects_max_distance(zones):
    far = pd.DataFrame({"lon": [3.0], "lat": [56.5]})
    assert pd.notna(nearest_zone(far, "lon", "lat", "EPSG:4326", zones).iloc[0])
    bounded = nearest_zone(far, "lon", "lat", "EPSG:4326", zones, max_distance_m=5_000.0)
    assert pd.isna(bounded.iloc[0])


def test_land_areas(zones):
    area = zone_land_area_km2(zones)
    assert set(area.index) == set(LAND_ZONES)
    assert 200_000 < area.sum() < 260_000, "GB land area is about 229,000 km2"
    assert area["Z14"] < area["Z2"], "London is smaller than North East Scotland"
