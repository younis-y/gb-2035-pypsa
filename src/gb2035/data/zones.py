"""Zone polygons and spatial assignment of point data to zones."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

LAND_ZONES: tuple[str, ...] = (
    "Z1_1",
    "Z1_2",
    "Z1_3",
    "Z1_4",
    "Z2",
    "Z3",
    "Z4",
    "Z5",
    "Z6",
    "Z7",
    "Z8",
    "Z9",
    "Z10",
    "Z11",
    "Z12",
    "Z13",
    "Z14",
    "Z15",
    "Z16",
    "Z17",
)
OFFSHORE_ZONES: tuple[str, ...] = ("DOGGER_BANK", "HORNSEA", "EAST_ANGLIA")
OFFSHORE_LANDING: dict[str, str] = {"DOGGER_BANK": "Z8", "HORNSEA": "Z8", "EAST_ANGLIA": "Z12"}
ZONE_LABELS: dict[str, str] = {
    "Z1_1": "Shetland",
    "Z1_2": "Western Isles",
    "Z1_3": "North Highlands",
    "Z1_4": "West Highlands",
    "Z2": "North East Scotland",
    "Z3": "Central Highlands",
    "Z4": "Argyll",
    "Z5": "Central Scotland",
    "Z6": "South Scotland",
    "Z7": "North England",
    "Z8": "Yorkshire and Humber",
    "Z9": "North West England and North Wales",
    "Z10": "Lincolnshire and East Midlands",
    "Z11": "Midlands",
    "Z12": "East Anglia and Central",
    "Z13": "South Wales and Severn",
    "Z14": "London",
    "Z15": "South East",
    "Z16": "South Central",
    "Z17": "South West peninsula",
    "DOGGER_BANK": "Dogger Bank (offshore)",
    "HORNSEA": "Hornsea (offshore)",
    "EAST_ANGLIA": "East Anglia (offshore)",
}
OSGB = "EPSG:27700"


def load_zones(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path).rename(columns={"Name_1": "zone"}).set_index("zone")
    gdf = gdf.to_crs("EPSG:4326")
    gdf["kind"] = ["offshore" if z in OFFSHORE_ZONES else "land" for z in gdf.index]
    unknown = set(gdf.index) - set(LAND_ZONES) - set(OFFSHORE_ZONES)
    if unknown:
        msg = f"unexpected zones in {path.name}: {sorted(unknown)}"
        raise ValueError(msg)
    return gdf[["geometry", "kind"]]


def _points(
    df: pd.DataFrame, x_col: str, y_col: str, crs: str, target_crs: str
) -> gpd.GeoDataFrame:
    pts = gpd.GeoDataFrame(
        index=df.index, geometry=gpd.points_from_xy(df[x_col], df[y_col]), crs=crs
    )
    return pts.to_crs(target_crs)


def assign_zone(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    crs: str,
    zones: gpd.GeoDataFrame,
    kinds: tuple[str, ...] = ("land",),
) -> pd.Series:
    """Zone containing each point, NaN when no polygon of the requested kinds contains it."""
    polys = zones[zones["kind"].isin(kinds)]
    pts = _points(df, x_col, y_col, crs, str(polys.crs))
    joined = gpd.sjoin(pts, polys[["geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    result: pd.Series = joined["zone"].reindex(df.index).astype(object)
    return result


def nearest_zone(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    crs: str,
    zones: gpd.GeoDataFrame,
    kinds: tuple[str, ...] = ("land",),
    max_distance_m: float | None = None,
) -> pd.Series:
    """Nearest zone of the requested kinds, measured in EPSG:27700 metres.

    With the default ``max_distance_m=None`` every point gets a nearest zone,
    however far away. Passing a bound returns NaN for points further than that
    from every requested-kind polygon.
    """
    polys = zones[zones["kind"].isin(kinds)].to_crs(OSGB)
    pts = _points(df, x_col, y_col, crs, OSGB)
    joined = gpd.sjoin_nearest(pts, polys[["geometry"]], how="left", max_distance=max_distance_m)
    joined = joined[~joined.index.duplicated(keep="first")]
    result: pd.Series = joined["zone"].reindex(df.index).astype(object)
    return result


def zone_land_area_km2(zones: gpd.GeoDataFrame) -> pd.Series:
    land = zones[zones["kind"] == "land"].to_crs(OSGB)
    result: pd.Series = (land.geometry.area / 1e6).rename("area_km2")
    return result
