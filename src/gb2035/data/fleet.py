"""Existing thermal fleet and committed nuclear plants aggregated to zones."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import geopandas as gpd
import pandas as pd

from gb2035.data.zones import assign_zone, nearest_zone

THERMAL_TYPES: dict[str, str] = {"CCGT": "ccgt", "OCGT": "ocgt"}
# Coastline generalisation misses are sub-kilometre (Hinkley Point C is 372m outside its
# polygon); Northern Ireland is about 40km from the nearest GB zone. 5km snaps the former
# without ever absorbing a genuinely wrong or non-GB coordinate.
COASTAL_SNAP_M = 5_000.0


def _read_stations(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="latin-1")
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    geo = (
        df["Geolocation"]
        .astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.split(",", expand=True)
        # a header-only (zero-row) file splits to zero float64 columns; restore the two
        # string columns .str.strip() below needs.
        .reindex(columns=range(2))
        .astype(object)
    )
    df["lat"] = pd.to_numeric(geo[0].str.strip(), errors="coerce")
    df["lon"] = pd.to_numeric(geo[1].str.strip(), errors="coerce")
    df["p_nom_mw"] = pd.to_numeric(df["Installed Capacity (MW)"], errors="coerce")
    df["technology"] = df["Type"].astype(str).str.strip().str.upper().map(THERMAL_TYPES)
    return df.dropna(subset=["lat", "lon", "p_nom_mw", "technology"])


def _read_committed(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["p_nom_mw"] = df["p_nom_mw"].astype(float)
    return df[["technology", "lat", "lon", "p_nom_mw"]]


def build_fleet_by_zone(
    stations_csv: Path, committed_csv: Path, zones: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Zone totals of existing CCGT and OCGT plus committed nuclear plants."""
    plants = pd.concat(
        [_read_stations(stations_csv), _read_committed(committed_csv)], ignore_index=True
    )
    plants["zone"] = assign_zone(plants, "lon", "lat", "EPSG:4326", zones)
    # Thermal and nuclear plants are sited at the water's edge for cooling; a coastline
    # generalised for a 20-zone map routinely cuts across the headland or estuary jetty
    # the plant sits on, so points that miss every polygon fall back to nearest zone.
    missing = plants["zone"].isna()
    if missing.any():
        plants.loc[missing, "zone"] = nearest_zone(
            plants.loc[missing], "lon", "lat", "EPSG:4326", zones, max_distance_m=COASTAL_SNAP_M
        )
    unassigned = plants.loc[plants["zone"].isna(), "p_nom_mw"].sum()
    if unassigned > 0.02 * plants["p_nom_mw"].sum():
        msg = f"{unassigned:.0f} MW of plant fell outside every zone polygon"
        raise ValueError(msg)
    # pandas-stubs types a single-column as_index=False groupby-sum as a Series, though at
    # runtime it is a DataFrame; cast so sort_values sees the DataFrame overload.
    grouped = cast(
        pd.DataFrame,
        plants.dropna(subset=["zone"])
        .groupby(["zone", "technology"], as_index=False)["p_nom_mw"]
        .sum(),
    )
    fleet = grouped.sort_values(["technology", "zone"], ignore_index=True)
    return fleet[["zone", "technology", "p_nom_mw"]]
