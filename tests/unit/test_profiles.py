from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from gb2035.config import weather_years
from gb2035.data.profiles import (
    clip_to_cutout,
    flatten_columns,
    load_profiles,
    unflatten_columns,
    validate_profiles,
)
from gb2035.data.zones import LAND_ZONES, OFFSHORE_ZONES


def synthetic(year: int = 2019) -> pd.DataFrame:
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    hours = np.arange(len(idx))
    cols = {}
    for z in LAND_ZONES:
        cols[("onwind", z)] = 0.3 + 0.2 * np.sin(hours / 24 * 2 * np.pi + hash(z) % 7)
        cols[("solar", z)] = np.clip(0.4 * np.sin((hours % 24 - 6) / 12 * np.pi), 0, 1)
        cols[("offwind", z)] = 0.45 + 0.2 * np.cos(hours / 24 * 2 * np.pi)
    for z in OFFSHORE_ZONES:
        cols[("offwind", z)] = 0.5 + 0.2 * np.cos(hours / 24 * 2 * np.pi)
    df = pd.DataFrame(cols, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns, names=["carrier", "zone"])
    return df.clip(0, 1)


def test_roundtrip_flatten(tmp_path: Path):
    df = synthetic()
    flat = flatten_columns(df)
    assert "onwind|Z7" in flat.columns
    flat.to_parquet(tmp_path / "cf.parquet")
    back = load_profiles(tmp_path / "cf.parquet")
    assert back.columns.names == ["carrier", "zone"]
    pd.testing.assert_frame_equal(back, df)
    pd.testing.assert_frame_equal(unflatten_columns(flat), df)


def test_validate_accepts_synthetic():
    validate_profiles(synthetic(), 2019)


def test_validate_rejects_out_of_range_and_missing():
    df = synthetic()
    bad = df.copy()
    bad.iloc[0, 0] = 1.5
    with pytest.raises(ValueError, match="range"):
        validate_profiles(bad, 2019)
    with pytest.raises(ValueError, match="missing"):
        validate_profiles(df.drop(columns=[("solar", "Z14")]), 2019)
    with pytest.raises(ValueError, match="hourly"):
        validate_profiles(df.iloc[:-1], 2019)


def test_validate_rejects_all_zero_column():
    df = synthetic()
    bad = df.copy()
    bad[("offwind", "EAST_ANGLIA")] = 0.0
    with pytest.raises(ValueError, match="all-zero"):
        validate_profiles(bad, 2019)


def test_clip_to_cutout_keeps_inside_geometry():
    bounds = (0.0, 0.0, 10.0, 10.0)
    inside = Polygon([(2, 2), (2, 4), (4, 4), (4, 2)])
    result = clip_to_cutout(inside, bounds)
    assert result.equals(inside)


def test_clip_to_cutout_buffers_outside_geometry():
    bounds = (0.0, 0.0, 10.0, 10.0)
    outside = Polygon([(10.3, 2), (10.3, 4), (10.5, 4), (10.5, 2)])
    result = clip_to_cutout(outside, bounds)
    assert not result.is_empty


def test_clip_to_cutout_raises_when_far_outside():
    bounds = (0.0, 0.0, 10.0, 10.0)
    far = Polygon([(15, 2), (15, 4), (16, 4), (16, 2)])
    with pytest.raises(ValueError):
        clip_to_cutout(far, bounds)


WEATHER_YEARS = weather_years(
    Path(__file__).resolve().parents[2] / "config" / "scenarios.yaml", 2019
)


@pytest.mark.slow
@pytest.mark.parametrize("year", WEATHER_YEARS)
def test_committed_profiles_are_plausible(repo_root: Path, year: int):
    cf = load_profiles(repo_root / "data" / "derived" / f"cf_{year}_zonal.parquet")
    validate_profiles(cf, year)
    means = cf.mean()
    onwind = means.xs("onwind", level="carrier")
    offwind = means.xs("offwind", level="carrier")
    solar = means.xs("solar", level="carrier")
    # Zonal annual means. The onshore ceiling is set by Shetland, Western Isles and Argyll,
    # where ERA5's ~25 km cells blend marine wind into small island zones: the windiest zone
    # reaches 0.615 in 2019 and 0.705 in 2022 (windy years run higher everywhere).
    assert onwind.between(0.15, 0.75).all()
    assert offwind.between(0.45, 0.70).all()
    assert solar.between(0.08, 0.15).all()
    # National means move with the weather year, but a units or regeneration bug would move
    # them far further: over 2010 to 2024 onshore runs 0.325 to 0.428 and solar 0.106 to 0.116.
    assert 0.30 < onwind.mean() < 0.45
    assert 0.10 < solar.mean() < 0.12
