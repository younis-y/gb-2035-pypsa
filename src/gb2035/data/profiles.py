"""Hourly capacity factors per zone from an atlite ERA5 cutout.

The Zenodo GB cutout (`data/raw/uk-2019.nc`) covers longitude -13.625 to
1.875 (cell edges). The East Anglia offshore zone polygon lies entirely
east of that boundary, so without correction atlite returns an all-zero
wind profile for it — which would also flatten every land zone's generic
offshore profile, since that is the mean of the three offshore polygons.
`build_profiles` clips every shape to the cutout's bounds before running
atlite (see `clip_to_cutout`), buffering outward in 0.25 degree steps for a
shape that falls outside entirely, so East Anglia's profile is drawn from
the nearest ERA5 cells just west of the polygon because the Zenodo GB
cutout ends at longitude 1.75. Separately, ERA5's coarse (~25 km) grid
inflates onshore capacity factors for small, fragmented island and coastal
zones by blending in marine boundary-layer wind: Shetland (Z1_1), the
Western Isles (Z1_2) and Argyll (Z4) all exceed 0.50 mean onshore CF as a
result, which is treated as a genuine feature of the input data rather than
a defect.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from gb2035.data.zones import LAND_ZONES, OFFSHORE_ZONES

SEP = "|"


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    columns = cast(pd.MultiIndex, df.columns)
    out.columns = pd.Index([f"{c}{SEP}{z}" for c, z in columns])
    return out


def unflatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = pd.MultiIndex.from_tuples(
        [tuple(str(c).split(SEP, 1)) for c in df.columns], names=["carrier", "zone"]
    )
    return out


def load_profiles(parquet: Path) -> pd.DataFrame:
    df = unflatten_columns(pd.read_parquet(parquet))
    # Parquet does not round-trip DatetimeIndex.freq; reattach it so a loaded
    # frame compares equal (via pd.testing.assert_frame_equal) to one built
    # in memory, and so callers get a clean hourly index rather than None.
    df.index = pd.DatetimeIndex(df.index, freq="h")
    return df


def validate_profiles(df: pd.DataFrame, year: int) -> None:
    expected_index = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    if len(df.index) != len(expected_index) or not df.index.equals(expected_index):
        msg = (
            f"profiles must be hourly over {year} ({len(expected_index)} rows), got {len(df.index)}"
        )
        raise ValueError(msg)
    if ((df < 0) | (df > 1)).any().any():
        msg = "capacity factors outside range [0, 1]"
        raise ValueError(msg)
    wanted = {("onwind", z) for z in LAND_ZONES} | {("solar", z) for z in LAND_ZONES}
    wanted |= {("offwind", z) for z in LAND_ZONES} | {("offwind", z) for z in OFFSHORE_ZONES}
    missing = wanted - set(df.columns)
    if missing:
        msg = f"profiles missing columns: {sorted(missing)[:5]}"
        raise ValueError(msg)
    columns = cast(pd.MultiIndex, df.columns)
    zero_cols = [col for col in columns if (df[col] == 0).all()]
    if zero_cols:
        names = [f"{c}{SEP}{z}" for c, z in zero_cols]
        msg = f"all-zero profile for {names[:5]}"
        raise ValueError(msg)


def clip_to_cutout(
    geometry: BaseGeometry,
    bounds: tuple[float, float, float, float],
    max_buffer_deg: float = 1.0,
) -> BaseGeometry:
    """Intersect `geometry` with the cutout's bounding box.

    A geometry entirely outside `bounds` is grown outward in 0.25 degree
    steps (up to `max_buffer_deg`) until it touches the box, so a shape just
    past the cutout's edge still yields a profile from the nearest covered
    cells instead of an empty one. Raises `ValueError` naming the geometry
    if it still does not intersect after the largest buffer step.
    """
    box_geom = box(*bounds)
    intersection = geometry.intersection(box_geom)
    step = 0.25
    buffer_deg = step
    while intersection.is_empty and buffer_deg <= max_buffer_deg + 1e-9:
        intersection = geometry.buffer(buffer_deg).intersection(box_geom)
        buffer_deg += step
    if intersection.is_empty:
        msg = (
            f"geometry with bounds {geometry.bounds} does not intersect cutout bounds "
            f"{bounds} even after buffering by {max_buffer_deg} degrees"
        )
        raise ValueError(msg)
    return intersection


def _clip_shapes(shapes: gpd.GeoSeries, bounds: tuple[float, float, float, float]) -> gpd.GeoSeries:
    """Clip every geometry in `shapes` to `bounds`, warning about large area changes."""
    clipped_values = shapes.apply(lambda geom: clip_to_cutout(geom, bounds))
    clipped = gpd.GeoSeries(clipped_values, index=shapes.index, crs=shapes.crs)
    for zone, original in shapes.items():
        change = abs(clipped[zone].area - original.area) / original.area
        if change > 0.05:
            warnings.warn(
                f"{zone}: clipped area differs from original by {change:.1%}",
                stacklevel=2,
            )
    return clipped


def build_profiles(
    cutout_path: Path,
    zones: gpd.GeoDataFrame,
    onshore_turbine: str = "Vestas_V112_3MW",
    offshore_turbine: str = "NREL_ReferenceTurbine_2020ATB_15MW_offshore",
    panel: str = "CSi",
) -> pd.DataFrame:
    """Run atlite once over the zone polygons. Requires the `profiles` extra.

    Shapes are clipped to the cutout's bounds before atlite runs; see the
    module docstring and `clip_to_cutout`.
    """
    import atlite

    cutout = atlite.Cutout(str(cutout_path))
    cminx, cminy, cmaxx, cmaxy = (float(v) for v in cutout.bounds)
    bounds = (cminx, cminy, cmaxx, cmaxy)
    shapes = zones.to_crs(cutout.crs).geometry
    land = shapes.loc[list(LAND_ZONES)]
    offshore = shapes.loc[list(OFFSHORE_ZONES)]
    land.index.name = offshore.index.name = "zone"
    land = _clip_shapes(land, bounds)
    offshore = _clip_shapes(offshore, bounds)

    onwind = cutout.wind(turbine=onshore_turbine, shapes=land, per_unit=True).to_pandas()
    solar = cutout.pv(
        panel=panel, orientation="latitude_optimal", shapes=land, per_unit=True
    ).to_pandas()
    offwind = cutout.wind(turbine=offshore_turbine, shapes=offshore, per_unit=True).to_pandas()
    generic_offshore = offwind.mean(axis=1)

    frames = {("onwind", z): onwind[z] for z in LAND_ZONES}
    frames |= {("solar", z): solar[z] for z in LAND_ZONES}
    frames |= {("offwind", z): offwind[z] for z in OFFSHORE_ZONES}
    frames |= {("offwind", z): generic_offshore for z in LAND_ZONES}
    df = pd.DataFrame(frames)
    df.columns = pd.MultiIndex.from_tuples(list(frames.keys()), names=["carrier", "zone"])
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df.index.name = None
    return df.clip(0.0, 1.0).astype("float64")
