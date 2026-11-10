"""The README's headline numbers, recomputed from committed files and found in the text.

Each claim is rendered from `results/`, `data/derived/` and `config/` exactly as the README
words it, so a re-solve that moves a number, or an edit that rewords one, fails here until the
two agree again. Qualitative claims ("not one megawatt", "never by electrolysis") are asserted
on the data as well as found in the text.
"""

from pathlib import Path

import pandas as pd
import pytest

from gb2035.config import load_scenario, load_settings
from gb2035.data.costs import annuity, capital_cost_per_yr, load_costs
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


def test_offshore_enters_only_where_the_readme_says(summary: pd.DataFrame):
    """Finding 3 names the only two runs that build greenfield offshore; a third would make
    it false."""
    builds = set(summary.index[summary["offwind_new_gw"] > 1e-3])
    assert builds == {"cap5_offwind_capex51", "cap5_fes_ceiling_import_100"}
    claim("No cap in the sweep builds greenfield offshore")


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


def _weather_runs() -> pd.DataFrame:
    rows = [
        pd.read_csv(p).iloc[0]
        for p in sorted((ROOT / "results_weather_years").glob("cap5_wy*/summary_row.csv"))
    ]
    return pd.DataFrame(rows).set_index("scenario")


def _offshore_capex_cut_percent(run: Path) -> float:
    """The cut to offshore's annualised capex that closes the best offshore unit's gap."""
    be = pd.read_csv(run / "breakeven.csv")
    off = be[(be["carrier"] == "offwind") & (be["component"] == "Generator")]
    gap = (off["capital_cost_gbp_per_mw_yr"] - off["market_value_gbp_per_mw_yr"]).min()
    costs = load_costs(ROOT / "data" / "derived" / "costs_2035_gb.csv").loc["offwind"]
    rate = load_settings(ROOT / "config" / "settings.yaml").discount_rate
    return 100 * gap / (annuity(rate, costs["lifetime_yr"]) * costs["capex_gbp"])


def test_every_weather_year_and_no_new_offshore_in_any():
    runs = _weather_runs()
    assert len(runs) == 15, "every year 2010 to 2024"
    assert runs["offwind_new_gw"].max() < 1e-3
    claim("Re-solved on all 15 weather years from 2010 to 2024")
    claim("builds no new offshore wind in any of them")
    cost, solar = runs["total_cost_gbp_bn_per_yr"], runs["solar_new_gw"]
    claim(f"its cost runs from {cost.min():.1f} to {cost.max():.1f} bn GBP/yr")
    claim(f"its new solar from {solar.min():.0f} to {solar.max():.0f} GW")


def test_the_offshore_capex_cut_across_weather_years():
    runs = sorted((ROOT / "results_weather_years").glob("cap5_wy*"))
    cuts = {run.name: _offshore_capex_cut_percent(run) for run in runs}
    claim(f"fall by {min(cuts.values()):.0f} to {max(cuts.values()):.0f} percent before its")
    assert min(cuts, key=cuts.__getitem__) == "cap5_wy2010", "least in 2010"


def test_the_breakeven_is_confirmed_either_side(summary: pd.DataFrame):
    short = summary.loc["cap5_offwind_capex64"]
    past = summary.loc["cap5_offwind_capex51"]
    assert short["offwind_new_gw"] < 1e-3
    claim(f"builds none; 49 percent lower builds {past['offwind_new_gw']:.1f} GW")
    cut = _offshore_capex_cut_percent(ROOT / "results" / "cap5")
    for name, side, percent in (
        ("cap5_offwind_capex64", 0.85, 36),
        ("cap5_offwind_capex51", 1.15, 49),
    ):
        factor = load_scenario(name, ROOT / "config" / "scenarios.yaml").capex_scale["offwind"]
        assert 100 * (1 - factor) == pytest.approx(percent, abs=0.5), "config matches the README"
        assert side * cut == pytest.approx(percent, abs=0.5), "15 percent either side of the cut"


def test_the_planning_ceiling_and_dear_imports(summary: pd.DataFrame):
    base, ceiling = summary.loc["cap5"], summary.loc["cap5_fes_ceiling"]
    both = summary.loc["cap5_fes_ceiling_import_100"]
    extra = ceiling["total_cost_gbp_bn_per_yr"] - base["total_cost_gbp_bn_per_yr"]
    claim(f"costs {extra:.1f} bn GBP/yr more and still builds no offshore")
    assert ceiling["offwind_new_gw"] < 1e-3
    assert ceiling["net_imports_twh"] > 2 * base["net_imports_twh"], "imports more than double"
    claim(
        f"brings in only {both['offwind_new_gw']:.1f} GW of offshore, beside "
        f"{both['gas_ccs_gw']:.1f} GW of gas CCS"
    )


def test_the_resolve_reproduces_cap5_to_the_penny():
    import json

    def total(path: str) -> float:
        return json.loads((ROOT / path / "run_meta.json").read_text())["total_cost_gbp_per_yr"]

    assert abs(total("results/cap5") - total("results_weather_years/cap5_wy2019")) < 0.01
    claim("re-solving `cap5` from scratch reproduces its cost to the penny")


FINDINGS = " ".join((ROOT / "docs" / "findings.md").read_text().split())


def finding(text: str) -> None:
    assert text in FINDINGS, f"docs/findings.md does not say: {text!r}"


def test_the_findings_weather_table_is_the_results():
    for run in sorted((ROOT / "results_weather_years").glob("cap5_wy*")):
        r = pd.read_csv(run / "summary_row.csv").iloc[0]
        year = int(run.name.removeprefix("cap5_wy"))
        label = f"{year} (lockdown demand)" if year in (2020, 2021) else str(year)
        finding(
            f"| {label} | {r['total_cost_gbp_bn_per_yr']:.1f} | "
            f"{r['shadow_carbon_price_gbp_per_t']:.0f} | {r['onwind_new_gw']:.1f} | "
            f"{r['solar_new_gw']:.1f} | {r['battery_new_gw']:.1f} | {r['offwind_new_gw']:.1f} | "
            f"{_offshore_capex_cut_percent(run):.0f} |"
        )


def test_the_findings_breakeven_and_planning_numbers(summary: pd.DataFrame):
    be = pd.read_csv(ROOT / "results" / "cap5" / "breakeven.csv").set_index("name")
    dogger = be.loc["offwind DOGGER_BANK"]
    share = dogger["market_value_gbp_per_mw_yr"] / dogger["capital_cost_gbp_per_mw_yr"]
    finding(
        f"earns {100 * share:.1f} percent of its "
        f"{dogger['capital_cost_gbp_per_mw_yr']:,.0f} GBP/MW-yr annual cost"
    )
    finding("a 42.6 percent capex cut")
    assert _offshore_capex_cut_percent(ROOT / "results" / "cap5") == pytest.approx(42.6, abs=0.05)
    ceiling = summary.loc["cap5_fes_ceiling"]
    finding(
        f"lifts the shadow carbon price from {summary.at['cap5', 'shadow_carbon_price_gbp_per_t']:.0f}"
        f" to {ceiling['shadow_carbon_price_gbp_per_t']:.0f} GBP/t"
    )
    finding(
        f"rise from {summary.at['cap5', 'net_imports_twh']:.1f} to "
        f"{ceiling['net_imports_twh']:.1f} TWh instead"
    )


def test_the_readme_counts_the_committed_runs():
    runs = [
        m
        for f in ("results", "results_hourly", "results_weather_years")
        for m in (ROOT / f).glob("*/run_meta.json")
    ]
    claim(f"eight checks on each of the {len(runs)} committed runs")
