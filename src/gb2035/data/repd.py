"""Renewable Energy Planning Database: operational and under-construction capacity by zone."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import geopandas as gpd
import pandas as pd

from gb2035.data.zones import OFFSHORE_LANDING, OSGB, assign_zone, nearest_zone

REPD_TECH: dict[str, str] = {
    "Wind Onshore": "onwind",
    "Wind Offshore": "offwind",
    "Solar Photovoltaics": "solar",
    "Battery": "battery",
    "Pumped Storage Hydroelectricity": "pumped_hydro",
}
REPD_STATUS: dict[str, str] = {
    "Operational": "operational",
    "Under Construction": "under_construction",
}


def _read_repd(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="latin-1", low_memory=False)
    df["technology"] = df["Technology Type"].map(REPD_TECH)
    df["status"] = df["Development Status (short)"].map(REPD_STATUS)
    df["p_nom_mw"] = pd.to_numeric(df["Installed Capacity (MWelec)"], errors="coerce")
    df["x"] = pd.to_numeric(df["X-coordinate"], errors="coerce")
    df["y"] = pd.to_numeric(df["Y-coordinate"], errors="coerce")
    df["country"] = df["Country"].astype(str).str.strip()
    keep = df["technology"].notna() & df["status"].notna() & (df["country"] != "Northern Ireland")
    return df.loc[keep].dropna(subset=["p_nom_mw", "x", "y"]).copy()


def build_repd_by_zone(repd_csv: Path, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate REPD capacity to zones; offshore wind is attributed to its landing zone."""
    df = _read_repd(repd_csv)
    df["zone"] = assign_zone(df, "x", "y", OSGB, zones, kinds=("land",))
    offshore = df["technology"] == "offwind"
    in_offshore_poly = assign_zone(df[offshore], "x", "y", OSGB, zones, kinds=("offshore",))
    df.loc[offshore, "zone"] = in_offshore_poly.map(OFFSHORE_LANDING).fillna(
        df.loc[offshore, "zone"]
    )
    missing = df["zone"].isna()
    if missing.any():
        df.loc[missing, "zone"] = nearest_zone(df[missing], "x", "y", OSGB, zones, kinds=("land",))
    # pandas-stubs types a single-column as_index=False groupby-sum as a Series, though at
    # runtime it is a DataFrame; cast so sort_values sees the DataFrame overload.
    grouped = cast(
        pd.DataFrame,
        df.groupby(["zone", "technology", "status"], as_index=False)["p_nom_mw"].sum(),
    )
    out = grouped.sort_values(["technology", "status", "zone"], ignore_index=True)
    return out[["zone", "technology", "status", "p_nom_mw"]]
