from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

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


@pytest.mark.slow
def test_committed_profiles_are_plausible(repo_root: Path):
    path = repo_root / "data" / "derived" / "cf_2019_zonal.parquet"
    if not path.exists():
        pytest.skip("profiles not built yet")
    cf = load_profiles(path)
    validate_profiles(cf, 2019)
    means = cf.mean()
    # 0.65 upper bound: Shetland/Western Isles/Argyll exceed 0.50 due to ERA5 coastal wind blending.
    assert means.xs("onwind", level="carrier").between(0.15, 0.65).all()
    assert means.xs("offwind", level="carrier").between(0.35, 0.65).all()
    assert means.xs("solar", level="carrier").between(0.08, 0.14).all()
