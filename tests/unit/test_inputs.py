from pathlib import Path

import pytest

from gb2035.model.inputs import load_inputs, offshore_units
from gb2035.paths import ProjectPaths


@pytest.fixture(scope="module")
def inputs(repo_root: Path):
    return load_inputs(ProjectPaths(repo_root))


def test_topology(inputs):
    assert len(inputs.buses) == 20
    assert len(inputs.links) == 31, "interconnector rows are excluded from inter-zone links"
    assert (
        inputs.links["bus0"].str.startswith("Z").all()
        and inputs.links["bus1"].str.startswith("Z").all()
    )
    assert len(inputs.interconnectors) == 14
    assert inputs.link_distance_km["Z7-Z2"] == pytest.approx(305.0)
    assert inputs.link_distance_km["Z9-Z3"] == pytest.approx(418.0)


def test_tables_present(inputs):
    assert set(inputs.fleet["technology"]) == {"ccgt", "ocgt", "nuclear"}
    assert {"onwind", "offwind", "solar", "battery", "pumped_hydro"} <= set(
        inputs.repd["technology"]
    )
    assert len(inputs.demand) == 8760
    assert inputs.weights.sum() == pytest.approx(1.0)
    assert ("onwind", "Z7") in inputs.profiles.columns
    assert "electrolysis" in inputs.costs.index
    assert "consumer_demand_twh" in set(inputs.fes["metric"])


def test_offshore_units(inputs):
    units = offshore_units(inputs.caps)
    assert ("DOGGER_BANK", "Z8", "DOGGER_BANK") in units
    assert ("EAST_ANGLIA", "Z12", "EAST_ANGLIA") in units
    assert ("Z2", "Z2", "Z2") in units
    assert sum(inputs.caps.offwind_shares.values()) == pytest.approx(1.0)
