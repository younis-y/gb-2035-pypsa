"""The committed results are the evidence behind the README, so they are tested like code.

Everything here reads only what is in the repository. Each run's tables must agree with each
other and with the physics (energy balance, the CO2 cap, additive costs); the summaries and the
README's generated table must match the runs; and every run must still be the network the
current code builds, so a change that would move a published number fails CI until that
scenario is re-solved.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from gb2035.config import load_scenario, load_settings
from gb2035.data.demand import demand_target_twh
from gb2035.data.fes import load_fes
from gb2035.model.inputs import load_inputs
from gb2035.model.network import build_network, network_fingerprint
from gb2035.paths import ProjectPaths
from gb2035.report.readme import END, START, summary_markdown
from gb2035.results.summary import summarise

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "config" / "scenarios.yaml"
FOLDERS = ("results", "results_hourly", "results_weather_years")
RUNS = sorted(meta.parent for f in FOLDERS for meta in (ROOT / f).glob("*/run_meta.json"))
TABLES = (
    "capacities",
    "energy",
    "emissions",
    "costs",
    "duals",
    "flows",
    "curtailment",
    "hydrogen",
    "summary_row",
    "breakeven",
)


@pytest.fixture(params=RUNS, ids=lambda run: f"{run.parent.name}/{run.name}")
def run(request: pytest.FixtureRequest) -> Path:
    return request.param


def _meta(run: Path) -> dict:
    return json.loads((run / "run_meta.json").read_text())


def test_every_run_has_its_tables_and_metadata(run: Path):
    for table in TABLES:
        assert (run / f"{table}.csv").exists(), table
    meta = _meta(run)
    assert meta["scenario"] == run.name
    assert meta["solver"] in {"pdlp", "hipdlp", "simplex"}
    assert meta["resolution_hours"] == (1 if run.parent.name == "results_hourly" else 3)
    assert meta["snapshots"] * meta["resolution_hours"] in {8760, 8784}, "a full year"


def test_ac_energy_balances_against_the_demand_the_model_saw(run: Path):
    """Every AC row of energy.csv is a net injection, so together they must equal AC demand:
    the FES total with the losses uplift, sampled at the run's resolution, plus any steel load."""
    settings = load_settings(ROOT / "config" / "settings.yaml")
    scenario = load_scenario(run.name, SCENARIOS)
    meta = _meta(run)
    year = scenario.weather_year or settings.weather_year
    national = pd.read_parquet(ROOT / "data" / "derived" / f"demand_{year}_hourly.parquet")
    national = national["gross_demand_mw"]
    fes = load_fes(ROOT / "data" / "derived" / "fes2025_gb_2035.csv")
    target = demand_target_twh(fes, scenario.demand_pathway, settings.losses_uplift)
    sampled = national.iloc[:: meta["resolution_hours"]]
    expected = target * sampled.sum() / national.sum() * len(national) / len(sampled)
    if scenario.steel is not None:
        expected += scenario.steel.port_talbot_eaf_twh + scenario.steel.scunthorpe_eaf_twh
    energy = pd.read_csv(run / "energy.csv")
    ac_twh = energy.loc[energy["bus_carrier"] == "AC", "twh"].sum()
    assert ac_twh == pytest.approx(expected, rel=2e-4)


def test_emissions_respect_the_cap_and_a_priced_cap_binds(run: Path):
    scenario = load_scenario(run.name, SCENARIOS)
    row = pd.read_csv(run / "summary_row.csv").iloc[0]
    if scenario.co2_cap_mt is None:
        return
    assert row["emissions_mt"] <= scenario.co2_cap_mt * (1 + 1e-4)
    assert row["shadow_carbon_price_gbp_per_t"] >= 0
    if row["shadow_carbon_price_gbp_per_t"] > 1.0:
        assert row["emissions_mt"] == pytest.approx(scenario.co2_cap_mt, rel=1e-3), (
            "complementary slackness: a cap with a price must be met exactly"
        )


def test_cost_breakdown_adds_up_to_the_total(run: Path):
    costs = pd.read_csv(run / "costs.csv")
    parts = costs.loc[~costs["is_memo"], "gbp_per_yr"].sum()
    total = costs.loc[costs["kind"] == "total", "gbp_per_yr"].iloc[0]
    assert parts == pytest.approx(total, rel=1e-6)
    summary = pd.read_csv(run / "summary_row.csv").iloc[0]
    assert summary["total_cost_gbp_bn_per_yr"] == pytest.approx(total / 1e9, rel=1e-5)


def test_every_unit_earns_what_optimality_requires(run: Path):
    """The LP's optimality conditions in market terms, checked on each committed solution at its
    own prices: a unit built below its cap earns exactly its annual cost, one held at its cap
    earns at least that, and an unbuilt one earns no more. A FES ceiling adds its rent to the
    cost of the carriers it holds. PDLP meets these to well inside 1e-3 of the dearest unit's
    cost; a solution or price that had drifted would not."""
    be = pd.read_csv(run / "breakeven.csv")
    duals = pd.read_csv(run / "duals.csv")
    rent = duals[duals["metric"] == "fes_ceiling_rent_gbp_per_mw_yr"].set_index("zone")["value"]
    cost = be["capital_cost_gbp_per_mw_yr"] + be["carrier"].map(rent).fillna(0.0)
    gap = be["market_value_gbp_per_mw_yr"] - cost
    tol = 1e-3 * be["capital_cost_gbp_per_mw_yr"].max()
    interior = (be["built_mw"] > 1.0) & (be["built_mw"] < be["max_mw"] - 1.0)
    at_cap = be["built_mw"] >= be["max_mw"] - 1.0
    unbuilt = be["built_mw"] < 1e-3
    assert interior.any()
    assert gap[interior].abs().max() < tol
    assert (gap[at_cap] > -tol).all()
    assert (gap[unbuilt] < tol).all()


@pytest.mark.parametrize("folder", [f for f in FOLDERS if (ROOT / f / "summary.csv").exists()])
def test_each_summary_is_its_runs(folder: str):
    committed = pd.read_csv(ROOT / folder / "summary.csv")
    fresh = summarise(ROOT / folder)
    pd.testing.assert_frame_equal(committed, fresh, check_exact=False, rtol=1e-5)


def test_readme_table_is_generated_from_results():
    readme = (ROOT / "README.md").read_text()
    block = readme.split(START, 1)[1].split(END, 1)[0].strip()
    assert block == summary_markdown(summarise(ROOT / "results"))


@pytest.mark.slow
def test_every_run_is_still_the_network_the_code_builds(run: Path):
    """The input fingerprint in run_meta.json is a hash of the unsolved network. If data, config
    or model code has changed what this scenario builds, its published numbers are stale."""
    settings = load_settings(ROOT / "config" / "settings.yaml")
    meta = _meta(run)
    settings = settings.model_copy(update={"resolution_hours": meta["resolution_hours"]})
    scenario = load_scenario(run.name, SCENARIOS)
    inputs = load_inputs(ProjectPaths(ROOT), scenario.weather_year or settings.weather_year)
    n = build_network(inputs, scenario, settings)
    assert network_fingerprint(n) == meta["input_fingerprint"], (
        f"{run.name} no longer builds the network it was solved from; re-run it"
    )
