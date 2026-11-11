from pathlib import Path

import pandas as pd
import pytest

from gb2035.config import load_assumptions
from gb2035.model.inputs import load_inputs, offshore_units
from gb2035.paths import ProjectPaths


@pytest.fixture(scope="module")
def inputs(repo_root: Path):
    return load_inputs(ProjectPaths(repo_root), 2019)


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


def test_load_inputs_reads_the_requested_weather_year(inputs):
    """Weather and demand come from the same calendar year, the one asked for."""
    assert inputs.demand.index[0] == inputs.profiles.index[0] == pd.Timestamp("2019-01-01")


def test_load_inputs_reads_another_year_not_2019(repo_root: Path):
    """The original bug: the model read the 2019 files whatever year was configured."""
    leap = load_inputs(ProjectPaths(repo_root), 2012)
    for series in (leap.demand, leap.profiles):
        assert len(series) == 8784
        assert series.index[0] == pd.Timestamp("2012-01-01")


def test_load_inputs_names_the_build_step_for_a_missing_year(repo_root: Path):
    with pytest.raises(FileNotFoundError, match="build-profiles --weather-year 1999"):
        load_inputs(ProjectPaths(repo_root), 1999)


def test_offshore_units(inputs):
    units = offshore_units(inputs.caps)
    assert ("DOGGER_BANK", "Z8", "DOGGER_BANK") in units
    assert ("EAST_ANGLIA", "Z12", "EAST_ANGLIA") in units
    assert ("Z2", "Z2", "Z2") in units
    assert sum(inputs.caps.offwind_shares.values()) == pytest.approx(1.0)


def test_caps_match_assumptions(inputs, repo_root: Path):
    """Every national cap and offshore share is a sourced entry in assumptions.yaml."""
    a = load_assumptions(repo_root / "config" / "assumptions.yaml")
    caps = inputs.caps
    assert caps.onwind_national_gw == a["onshore_cap_national_gw"].value
    assert caps.solar_national_gw == a["solar_cap_national_gw"].value
    assert caps.offwind_national_gw == a["offshore_cap_national_gw"].value
    polygons = {
        "DOGGER_BANK": "offwind_share_dogger_bank",
        "HORNSEA": "offwind_share_hornsea",
        "EAST_ANGLIA": "offwind_share_east_anglia",
    }
    for unit, key in polygons.items():
        assert caps.offwind_shares[unit] == pytest.approx(a[key].value)
    other = sum(v for k, v in caps.offwind_shares.items() if k not in polygons)
    assert other == pytest.approx(a["offwind_share_other_coastal"].value)
