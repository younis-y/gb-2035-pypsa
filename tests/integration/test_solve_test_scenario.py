import json
from pathlib import Path

import pytest

from gb2035.config import load_scenario, load_settings
from gb2035.model.inputs import load_inputs
from gb2035.model.network import build_network
from gb2035.model.solve import solve
from gb2035.paths import ProjectPaths
from gb2035.results.extract import (
    capacities,
    costs,
    dispatch_hourly,
    energy,
    extract_all,
    shadow_carbon_price,
    write_results,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def solved(repo_root: Path):
    paths = ProjectPaths(repo_root)
    settings = load_settings(paths.config / "settings.yaml")
    inputs = load_inputs(paths)
    scenario = load_scenario("test", paths.config / "scenarios.yaml")
    n = build_network(inputs, scenario, settings)
    result = solve(n, settings)
    return n, result, scenario


def test_optimal(solved):
    n, result, _ = solved
    assert result.status == "ok" and result.condition == "optimal"
    assert result.total_cost_gbp_per_yr > 0
    assert result.fixed_asset_cost_gbp_per_yr > 0, "sunk *_existing units carry real fixed O&M"
    assert result.total_cost_gbp_per_yr > result.lp_objective_gbp_per_yr
    capex_plus_opex = float(n.statistics.capex().sum()) + float(
        n.statistics.opex(groupby_time="sum").sum()
    )
    assert result.total_cost_gbp_per_yr == pytest.approx(capex_plus_opex, rel=1e-6), (
        "the reported total must reconcile with PyPSA's own accounting"
    )


def test_energy_balance_closes(solved):
    n, *_ = solved
    demand = n.get_switchable_as_dense("Load", "p_set").sum().sum()
    balance = n.statistics.energy_balance(groupby_time="sum")
    per_bus_carrier = balance.groupby(level="bus_carrier").sum()
    assert abs(per_bus_carrier["AC"]) < 1e-3 * demand
    assert abs(per_bus_carrier["H2"]) < 1e-3 * demand


def test_cap_binds_and_dual_positive(solved):
    n, _, scenario = solved
    weights = n.snapshot_weightings["generators"]
    emissions_t = 0.0
    for name, g in n.generators.iterrows():
        co2 = float(n.carriers.at[g["carrier"], "co2_emissions"])
        if co2 > 0:
            emissions_t += float((n.generators_t.p[name] / g["efficiency"] * weights).sum()) * co2
    assert emissions_t / 1e6 == pytest.approx(scenario.co2_cap_mt, rel=0.01)
    assert shadow_carbon_price(n) > 0


def test_capacities_flag_every_sunk_unit(solved):
    n, *_ = solved
    caps = capacities(n)
    for carrier in ("import", "nuclear", "pumped_hydro", "AC", "DC"):
        rows = caps[caps["carrier"] == carrier]
        assert not rows.empty and rows["existing"].all(), f"{carrier} is fixed, not new build"
    retiring = caps[caps["name"].str.startswith("ccgt_existing")]
    assert not retiring.empty and retiring["existing"].all(), "the retiring fleet is still existing"
    greenfield = caps[caps["name"].str.match(r"^(onwind|solar|battery) Z")]
    assert not greenfield.empty and not greenfield["existing"].any()


def test_energy_rows_state_their_commodity(solved):
    n, *_ = solved
    table = energy(n).set_index("carrier")
    assert table.at["blue_h2", "bus_carrier"] == "H2", "blue hydrogen is not electricity"
    assert table.at["onwind", "bus_carrier"] == "AC"
    assert table.at["h2_turbine", "bus_carrier"] == "AC"
    assert table.at["electrolysis", "twh"] <= 0, "electrolysis draws power, it does not supply it"


def test_dispatch_hourly_balances(solved):
    n, *_ = solved
    hourly = dispatch_hourly(n)
    assert "blue_h2" not in hourly.columns, "hydrogen MW must not be added to electricity MW"
    supply = hourly.drop(columns=["load", "price_mean_gbp_per_mwh"]).sum(axis=1)
    assert ((supply - hourly["load"]).abs() < 1e-3 * hourly["load"]).all()


def test_costs_are_additive(solved):
    n, result, _ = solved
    table = costs(n, result)
    component = float(table[~table["is_memo"]]["gbp_per_yr"].sum())
    memo = table[table["is_memo"]].set_index("kind")["gbp_per_yr"]
    total = float(memo["total"])
    assert component == pytest.approx(total, rel=1e-6), "capex plus opex is the whole cost"
    assert float(memo["memo_lp_objective"]) + float(memo["memo_fixed_asset_fom"]) == pytest.approx(
        total, rel=1e-9
    )
    assert (table[table["is_memo"]]["note"] == "not additive with component rows").all()


def test_results_written_and_objective_stable(solved, tmp_path: Path, repo_root: Path):
    n, result, scenario = solved
    results = extract_all(n, scenario.name, result)
    paths = write_results(results, tmp_path / scenario.name)
    names = {p.name for p in paths}
    assert {
        "capacities.csv",
        "energy.csv",
        "emissions.csv",
        "costs.csv",
        "duals.csv",
        "flows.csv",
        "curtailment.csv",
        "hydrogen.csv",
        "dispatch_hourly.parquet",
        "summary_row.csv",
    } <= names
    assert results["capacities"]["p_nom_opt"].ge(0).all()
    costs_csv = (tmp_path / scenario.name / "costs.csv").read_text()
    assert "e+" not in costs_csv and "e-" not in costs_csv, "pounds, not scientific notation"
    assert results["hydrogen"].set_index("metric").at[
        "industrial_demand_twh", "value"
    ] == pytest.approx(5.0, rel=0.01)
    expected_path = repo_root / "tests" / "integration" / "expected_objective.json"
    expected = json.loads(expected_path.read_text())["test"]
    assert result.total_cost_gbp_per_yr == pytest.approx(expected, rel=0.005), (
        "regression guard; update the JSON deliberately if assumptions change"
    )
