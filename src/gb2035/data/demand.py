"""National hourly demand from NESO history, split to zones and scaled to a FES pathway."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gb2035.data.zones import LAND_ZONES

# The length of the model's year: snapshot weights always sum to it, whatever the weather year.
HOURS_PER_YEAR = 8760.0


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
    # Every year writes `01-JAN-2019` except 2023, which writes `01-Jan-23`.
    raw = df["SETTLEMENT_DATE"].str.title()
    four_digit = raw.str.len() == len("01-Jan-2019")
    date = pd.to_datetime(raw.where(four_digit), format="%d-%b-%Y").fillna(
        pd.to_datetime(raw.where(~four_digit), format="%d-%b-%y")
    )
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
    # The model weights every weather year as HOURS_PER_YEAR hours, so scale by the mean hour:
    # scaling a leap year's 8,784 hours by their sum delivered only 8760/8784 of the target.
    scale = target_twh * 1e6 / (national.mean() * HOURS_PER_YEAR)
    scaled = national * scale
    return pd.DataFrame({zone: scaled * w for zone, w in weights.items()}, index=national.index)


def demand_target_twh(fes: pd.DataFrame, pathway: str, losses_uplift: float) -> float:
    rows = fes[(fes["metric"] == "consumer_demand_twh") & (fes["pathway"] == pathway)]
    if rows.empty:
        msg = f"no consumer_demand_twh for pathway {pathway!r}"
        raise KeyError(msg)
    return float(rows["value"].iloc[0]) * losses_uplift
