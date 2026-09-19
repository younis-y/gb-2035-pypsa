from pathlib import Path

import numpy as np
import pytest

from gb2035.config import load_scenario, load_settings
from gb2035.model.inputs import load_inputs
from gb2035.model.network import build_network, select_snapshots
from gb2035.paths import ProjectPaths


@pytest.fixture(scope="module")
def built(repo_root: Path):
    paths = ProjectPaths(repo_root)
    settings = load_settings(paths.config / "settings.yaml")
    inputs = load_inputs(paths)
    scenario = load_scenario("test", paths.config / "scenarios.yaml")
    return build_network(inputs, scenario, settings), inputs, scenario, settings


def test_snapshot_selection(built):
    n, inputs, scenario, settings = built
    assert len(n.snapshots) == 168
    assert n.snapshots[0].strftime("%Y-%m-%d %H") == "2019-01-14 00"
    assert n.snapshot_weightings["objective"].sum() == pytest.approx(8760.0)
    assert (n.snapshot_weightings["stores"] == 1.0).all()
    full = select_snapshots(
        inputs.demand.index, scenario.model_copy(update={"snapshots": None}), settings
    )
    assert len(full) == 8760


def test_component_counts(built):
    n, *_ = built
    assert len(n.buses) == 21, "20 zones plus the Teesside hydrogen bus"
    assert (n.links.carrier.isin(["AC", "DC"])).sum() == 31
    assert (n.generators.carrier == "import").sum() == 14
    assert len(n.loads) == 21, "20 zonal loads plus industrial hydrogen"
    assert n.generators.carrier.notna().all() and (n.generators.carrier != "").all()
    assert (n.generators.p_nom_min <= n.generators.p_nom_max).all()
    assert "co2_cap" in n.global_constraints.index
    assert n.global_constraints.at["co2_cap", "constant"] == pytest.approx(5.0e6)
    # Brownfield capacity is a separate fixed unit per zone, so the totals are greenfield plus
    # one `*_existing` unit for every zone REPD gives capacity in: 20 + 20 onwind, 20 + 17 solar,
    # 9 + 12 offwind, 2 nuclear, 36 gas, 20 gas_ccs, 14 import, 1 blue_h2.
    assert len(n.generators) == 171
    assert len(n.storage_units) == 41, "20 + 18 battery plus 3 pumped hydro"
    assert len(n.stores) == 1


def test_existing_capacity_is_fixed_and_pays_fom_only(built):
    """REPD floors are sunk: fixed units charged FOM, never annuitised new-build capex."""
    n, inputs, *_ = built
    for tech in ("onwind", "solar", "offwind", "battery"):
        fom = float(
            inputs.costs.at["battery_inverter" if tech == "battery" else tech, "fom_gbp_per_yr"]
        )
        table = n.storage_units if tech == "battery" else n.generators
        existing = table[table.index.str.startswith(f"{tech}_existing ")]
        assert not existing.empty
        assert not existing["p_nom_extendable"].any(), f"{tech}_existing must not be extendable"
        assert (existing["p_nom"] > 0).all(), "zero-capacity units must not be added"
        assert existing["capital_cost"].eq(fom).all(), f"{tech}_existing must pay FOM only"
        greenfield = table[table.index.str.startswith(f"{tech} ")]
        assert greenfield["p_nom_extendable"].all()
        assert (greenfield["p_nom_min"] == 0.0).all(), "floors moved to the fixed units"
        assert greenfield["capital_cost"].gt(fom).all(), "greenfield pays annuitised capex + FOM"


def test_key_components(built):
    n, inputs, *_ = built
    assert (
        "electrolysis Teesside" in n.links.index
        and n.links.at["electrolysis Teesside", "bus0"] == "Z7"
    )
    assert "h2_store Teesside" in n.stores.index and n.stores.at["h2_store Teesside", "e_cyclic"]
    assert "h2_turbine Teesside" in n.links.index
    # Corrected expectation: the flat industrial load is a constant p_set, which PyPSA keeps in the
    # static `loads` table rather than in `loads_t.p_set`. get_switchable_as_dense is the accessor
    # that broadcasts it over the snapshots, so this still reads the first hour's MW.
    h2_demand = n.get_switchable_as_dense("Load", "p_set")["h2_demand Teesside"]
    assert h2_demand.iloc[0] == pytest.approx(5.0e6 / 8760)
    assert "blue_h2 Teesside" in n.generators.index
    assert n.generators.at["nuclear Z12", "p_nom"] == pytest.approx(1198.0)
    assert not n.generators.at["nuclear Z12", "p_nom_extendable"]
    assert (
        n.generators.at["ccgt_existing Z9", "p_nom_extendable"]
        and n.generators.at["ccgt_existing Z9", "capital_cost"] > 0
    )
    assert n.storage_units.at["battery Z14", "max_hours"] == 2.0
    assert n.storage_units.at["battery Z14", "efficiency_store"] == pytest.approx(np.sqrt(0.9))
    assert n.storage_units.at["battery Z14", "p_nom_extendable"]
    assert not n.storage_units.at["battery_existing Z14", "p_nom_extendable"]
    assert n.storage_units.at["battery_existing Z14", "p_nom"] == pytest.approx(
        inputs.repd.query("zone == 'Z14' and technology == 'battery'")["p_nom_mw"].sum()
    )
    assert n.generators.loc[n.generators.carrier == "import", "p_nom"].sum() == pytest.approx(
        19_400.0
    )
    assert n.generators.at["offwind DOGGER_BANK", "bus"] == "Z8"
    # The REPD floor now lives on the fixed unit; the extendable generator is pure greenfield.
    assert n.generators.at["onwind Z7", "p_nom_min"] == 0.0
    assert not n.generators.at["onwind_existing Z7", "p_nom_extendable"]
    assert (
        n.generators.at["onwind_existing Z7", "p_nom"]
        == inputs.repd.query("zone == 'Z7' and technology == 'onwind'")["p_nom_mw"].sum()
    )
    # Every zone with REPD offshore capacity now carries it, including the six zones that no
    # configured offshore unit lands at (Z10, Z1_3, Z3, Z5, Z6, Z9).
    offwind_existing = n.generators.loc[n.generators.index.str.startswith("offwind_existing ")]
    assert offwind_existing["p_nom"].sum() == pytest.approx(
        inputs.repd.query("technology == 'offwind'")["p_nom_mw"].sum()
    )
    assert offwind_existing["p_nom"].sum() == pytest.approx(27_856.0)


def test_demand_energy_matches_target(built):
    n, *_ = built
    zonal = n.loads_t.p_set[[c for c in n.loads_t.p_set.columns if c.startswith("load ")]]
    weighted_twh = (zonal.sum(axis=1) * n.snapshot_weightings["objective"]).sum() / 1e6
    assert 350 < weighted_twh < 650, (
        "a winter week scaled to a year overshoots the 415 TWh annual target; order of magnitude only"
    )


def test_no_cap_no_price_scenario_has_no_constraint(repo_root: Path, built):
    _, inputs, scenario, settings = built
    free = scenario.model_copy(update={"co2_cap_mt": None, "name": "free"})
    n = build_network(inputs, free, settings)
    assert "co2_cap" not in n.global_constraints.index


def test_import_price_sensitivity_overrides_settings(repo_root: Path, built):
    n, inputs, scenario, settings = built
    paths = ProjectPaths(repo_root)
    import_scenario = load_scenario("cap5_import_100", paths.config / "scenarios.yaml")
    # Reuse the test scenario's one-week window so this stays a structural check, not a full year.
    n_100 = build_network(
        inputs, import_scenario.model_copy(update={"snapshots": scenario.snapshots}), settings
    )
    imports_100 = n_100.generators[n_100.generators["carrier"] == "import"]
    assert not imports_100.empty
    assert (imports_100["marginal_cost"] == 100.0).all()
    imports_test = n.generators[n.generators["carrier"] == "import"]
    assert not imports_test.empty
    assert (imports_test["marginal_cost"] == 65.0).all()


def test_tx_expansion_prices_every_link(repo_root: Path, built):
    _, inputs, scenario, settings = built
    paths = ProjectPaths(repo_root)
    tx_scenario = load_scenario("cap5_tx_expansion", paths.config / "scenarios.yaml")
    # Reuse the test scenario's one-week window so this stays a structural check, not a full year.
    n = build_network(
        inputs, tx_scenario.model_copy(update={"snapshots": scenario.snapshots}), settings
    )
    tx = n.links[n.links.carrier.isin(["AC", "DC"])]
    assert len(tx) == 31
    assert tx["p_nom_extendable"].all()
    assert (tx["capital_cost"] > 0).all()
    assert (tx["p_nom_min"] == tx["p_nom"]).all()
