"""National hourly demand from NESO history, split to zones and scaled to a FES pathway."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gb2035.data.zones import LAND_ZONES


def load_neso_demand(csv: Path, year: int) -> pd.Series:
    """Hourly gross underlying demand in MW for `year`.

    NESO's ND excludes embedded generation, so embedded wind and solar are added back to
    recover the demand a 2035 system has to meet. Half-hourly periods are stamped from the
    settlement date and period number, then averaged to hours; clock-change days therefore
    land one period early or late, which is immaterial for a capacity model.
    """
    df = pd.read_csv(
        csv,
        usecols=[
            "SETTLEMENT_DATE",
            "SETTLEMENT_PERIOD",
            "ND",
            "EMBEDDED_WIND_GENERATION",
            "EMBEDDED_SOLAR_GENERATION",
        ],
    )
    date = pd.to_datetime(df["SETTLEMENT_DATE"].str.title(), format="%d-%b-%Y")
    stamp = date + pd.to_timedelta((df["SETTLEMENT_PERIOD"] - 1) * 30, unit="min")
    gross = df["ND"] + df["EMBEDDED_WIND_GENERATION"] + df["EMBEDDED_SOLAR_GENERATION"]
    half_hourly = pd.Series(gross.to_numpy(dtype=float), index=stamp).sort_index()
    hourly = half_hourly.resample("h").mean()
    full = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h")
    return hourly.reindex(full).ffill().bfill().rename("gross_demand_mw")


def load_zone_weights(csv: Path) -> pd.Series:
    df = pd.read_csv(csv).set_index("zone")
    missing = set(LAND_ZONES) - set(df.index)
    if missing:
        msg = f"demand weights missing zones: {sorted(missing)}"
        raise ValueError(msg)
    w = df.loc[list(LAND_ZONES), "weight"].astype(float)
    return (w / w.sum()).rename("weight")


def build_zonal_demand(national: pd.Series, weights: pd.Series, target_twh: float) -> pd.DataFrame:
    scale = target_twh * 1e6 / national.sum()
    scaled = national * scale
    return pd.DataFrame({zone: scaled * w for zone, w in weights.items()}, index=national.index)


def demand_target_twh(fes: pd.DataFrame, pathway: str, losses_uplift: float) -> float:
    rows = fes[(fes["metric"] == "consumer_demand_twh") & (fes["pathway"] == pathway)]
    if rows.empty:
        msg = f"no consumer_demand_twh for pathway {pathway!r}"
        raise KeyError(msg)
    return float(rows["value"].iloc[0]) * losses_uplift
