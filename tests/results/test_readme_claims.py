"""The README's headline numbers, recomputed from committed files and found in the text.

Each claim is rendered from `results/`, `data/derived/` and `config/` exactly as the README
words it, so a re-solve that moves a number, or an edit that rewords one, fails here until the
two agree again. Qualitative claims ("not one megawatt", "never by electrolysis") are asserted
on the data as well as found in the text.
"""

from pathlib import Path

import pandas as pd
import pytest

from gb2035.config import load_settings
from gb2035.data.costs import capital_cost_per_yr, load_costs
from gb2035.data.profiles import load_profiles

ROOT = Path(__file__).resolve().parents[2]
README = " ".join((ROOT / "README.md").read_text().split())
SWEEP = ["uncapped", "cap30", "cap20", "cap10", "cap5", "cap2"]


@pytest.fixture(scope="module")
def summary() -> pd.DataFrame:
    return pd.read_csv(ROOT / "results" / "summary.csv").set_index("scenario")


@pytest.fixture(scope="module")
def fes() -> pd.Series:
    df = pd.read_csv(ROOT / "data" / "derived" / "fes2025_gb_2035.csv")
    return df[df["pathway"] == "Holistic Transition"].set_index("metric")["value"]


def levelised_gbp_mwh(technology: str, capacity_factor: float) -> float:
    """Annuitised capex plus fixed O&M over a year's output, plus variable O&M."""
    costs = load_costs(ROOT / "data" / "derived" / "costs_2035_gb.csv")
    rate = load_settings(ROOT / "config" / "settings.yaml").discount_rate
    annual = capital_cost_per_yr(costs, technology, rate)
    return annual / (capacity_factor * 8760) + float(costs.at[technology, "vom_gbp_per_mwh"])


def claim(text: str) -> None:
    assert text in README, f"README does not say: {text!r}"


def test_the_cap5_system(summary: pd.DataFrame):
    c = summary.loc["cap5"]
    claim(f"cap costs {c['total_cost_gbp_bn_per_yr']:.1f} bn GBP/yr")
    claim(
        f"{c['onwind_gw']:.1f} GW of onshore wind and {c['solar_gw']:.1f} GW of solar against "
        f"{c['offwind_gw']:.1f} GW of offshore"
    )


def test_no_new_offshore_anywhere_in_the_sweep(summary: pd.DataFrame):
    claim("not one megawatt of new offshore is built at any cap in the sweep")
    assert summary.loc[SWEEP, "offwind_new_gw"].max() < 1e-3


def test_the_fes_comparison(summary: pd.DataFrame, fes: pd.Series):
    claim(f"reaches {fes['offshore_wind_gw']:.1f} GW of offshore by 2035")


def test_the_levelised_costs_where_the_model_stops():
    """The dearest onshore zone `cap2` builds in, against the cheapest offshore site."""
    cf = load_profiles(ROOT / "data" / "derived" / "cf_2019_zonal.parquet").mean()
    caps = pd.read_csv(ROOT / "results" / "cap2" / "capacities.csv")
    built = caps[(caps["carrier"] == "onwind") & ~caps["existing"] & (caps["p_nom_opt"] > 1.0)]
    onshore = max(levelised_gbp_mwh("onwind", cf[("onwind", z)]) for z in built["zone"])
    offshore = min(
        levelised_gbp_mwh("offwind", cf[("offwind", site)])
        for site in ("DOGGER_BANK", "HORNSEA", "EAST_ANGLIA")
    )
    claim(
        f"onshore zones costing about {onshore:.0f} GBP/MWh before it will buy a megawatt of "
        f"offshore at {offshore:.0f}"
    )


def test_the_cost_of_tightening_the_cap(summary: pd.DataFrame):
    rise = (
        summary.at["cap2", "total_cost_gbp_bn_per_yr"]
        - summary.at["cap30", "total_cost_gbp_bn_per_yr"]
    )
    low = summary.at["cap30", "shadow_carbon_price_gbp_per_t"]
    high = summary.at["cap2", "shadow_carbon_price_gbp_per_t"]
    claim(
        f"adds {rise:.1f} bn GBP/yr and lifts the shadow carbon price from {low:.0f} to {high:.0f} GBP/t"
    )


def test_electrolysis_is_never_built(summary: pd.DataFrame):
    assert summary["electrolysis_gw"].max() < 1e-6
    assert summary["teesside_green_h2_twh"].max() < 1e-6
