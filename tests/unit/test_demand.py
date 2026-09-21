from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gb2035.data.demand import (
    build_zonal_demand,
    demand_target_twh,
    load_neso_demand,
    load_zone_weights,
)
from gb2035.data.zones import LAND_ZONES


def make_sample(path: Path) -> None:
    rows = []
    for day, periods in (("01-JAN-2019", 48), ("02-JAN-2019", 46)):
        for p in range(1, periods + 1):
            rows.append(
                {
                    "SETTLEMENT_DATE": day,
                    "SETTLEMENT_PERIOD": p,
                    "ND": 20000 + 100 * p,
                    "EMBEDDED_WIND_GENERATION": 1000,
                    "EMBEDDED_SOLAR_GENERATION": 0,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_load_neso_demand_hourly_gross(tmp_path: Path):
    make_sample(tmp_path / "d.csv")
    s = load_neso_demand(tmp_path / "d.csv", year=2019)
    assert s.name == "gross_demand_mw"
    assert len(s) == 8760, "reindexed to the full year, gaps forward-filled"
    assert s.index[0] == pd.Timestamp("2019-01-01 00:00")
    assert s.iloc[0] == pytest.approx((20100 + 20200) / 2 + 1000)
    assert not s.isna().any()


def test_zone_weights(repo_root: Path):
    w = load_zone_weights(repo_root / "config" / "demand_weights.csv")
    assert set(w.index) == set(LAND_ZONES)
    assert w.sum() == pytest.approx(1.0)
    assert w["Z14"] > w["Z1_1"]


def test_build_zonal_demand_scales_and_splits(repo_root: Path):
    idx = pd.date_range("2019-01-01", periods=8760, freq="h")
    national = pd.Series(np.full(8760, 30_000.0), index=idx, name="gross_demand_mw")
    w = load_zone_weights(repo_root / "config" / "demand_weights.csv")
    zonal = build_zonal_demand(national, w, target_twh=415.5)
    assert list(zonal.columns) == list(w.index)
    assert zonal.to_numpy().sum() / 1e6 == pytest.approx(415.5)
    assert zonal["Z14"].iloc[0] / zonal.iloc[0].sum() == pytest.approx(w["Z14"])


def test_demand_target_twh():
    fes = pd.DataFrame(
        {
            "metric": ["consumer_demand_twh"] * 2,
            "pathway": ["Holistic Transition", "Electric Engagement"],
            "value": [388.303, 407.789],
        }
    )
    assert demand_target_twh(fes, "Holistic Transition", 1.07) == pytest.approx(415.48, abs=0.01)
    with pytest.raises(KeyError):
        demand_target_twh(fes, "Falling Behind", 1.07)
