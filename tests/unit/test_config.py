from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gb2035.config import (
    HydrogenSettings,
    Scenario,
    Settings,
    SteelSettings,
    deep_merge,
    list_scenarios,
    load_assumptions,
    load_scenario,
    load_settings,
)
from gb2035.paths import ProjectPaths


def test_project_paths(tmp_path: Path):
    p = ProjectPaths(tmp_path)
    assert p.config == tmp_path / "config"
    assert p.data_raw == tmp_path / "data" / "raw"
    assert p.data_derived == tmp_path / "data" / "derived"
    assert p.results == tmp_path / "results"
    assert p.manifest == tmp_path / "data" / "manifest.json"


def test_settings_defaults():
    s = Settings()
    assert s.weather_year == 2019
    assert s.discount_rate == 0.07
    assert s.solver_name == "highs"


def test_deep_merge_nested():
    base = {"a": 1, "h": {"x": 1, "y": 2}}
    assert deep_merge(base, {"h": {"y": 5}, "b": 2}) == {"a": 1, "b": 2, "h": {"x": 1, "y": 5}}
    assert base == {"a": 1, "h": {"x": 1, "y": 2}}, "deep_merge must not mutate its input"


def test_scenario_rejects_cap_and_price_together():
    with pytest.raises(ValidationError):
        Scenario(
            name="bad",
            co2_cap_mt=5.0,
            carbon_price_gbp_t=55.0,
            demand_pathway="Holistic Transition",
        )


def test_scenario_allows_neither_cap_nor_price():
    s = Scenario(name="free", demand_pathway="Holistic Transition")
    assert s.co2_cap_mt is None and s.carbon_price_gbp_t is None


def test_scenario_interconnector_price_overrides_default_none():
    s = Scenario(name="free", demand_pathway="Holistic Transition")
    assert s.interconnector_import_price_gbp_mwh is None
    assert s.interconnector_export_price_gbp_mwh is None
    priced = Scenario(
        name="priced",
        demand_pathway="Holistic Transition",
        interconnector_import_price_gbp_mwh=100.0,
    )
    assert priced.interconnector_import_price_gbp_mwh == 100.0
    assert priced.interconnector_export_price_gbp_mwh is None, "one direction may move alone"


def test_settings_price_imports_above_exports():
    """Exports must clear at or below the import price, or the model round-trips for free money."""
    s = Settings()
    assert s.interconnector_import_price_gbp_mwh == 65.0
    assert s.interconnector_export_price_gbp_mwh == 45.0
    with pytest.raises(ValidationError):
        Settings(
            interconnector_import_price_gbp_mwh=45.0,
            interconnector_export_price_gbp_mwh=65.0,
        )
    equal = Settings(
        interconnector_import_price_gbp_mwh=60.0, interconnector_export_price_gbp_mwh=60.0
    )
    assert equal.interconnector_export_price_gbp_mwh == 60.0, "equal prices are not arbitrage"


def test_load_scenario_merges_defaults(tmp_path: Path):
    doc = {
        "defaults": {
            "demand_pathway": "Holistic Transition",
            "hydrogen": {"industrial_demand_twh": 5.0},
        },
        "scenarios": {
            "cap5": {"description": "cap", "co2_cap_mt": 5.0},
            "cap5_no_h2": {"co2_cap_mt": 5.0, "hydrogen": {"industrial_demand_twh": 0.0}},
        },
    }
    path = tmp_path / "scenarios.yaml"
    path.write_text(yaml.safe_dump(doc))
    s = load_scenario("cap5_no_h2", path)
    assert s.name == "cap5_no_h2"
    assert s.co2_cap_mt == 5.0
    assert s.hydrogen.industrial_demand_twh == 0.0
    assert s.hydrogen.bus_zone == "Z7"
    assert list_scenarios(path) == ["cap5", "cap5_no_h2"]


def test_load_scenario_unknown_name(tmp_path: Path):
    path = tmp_path / "scenarios.yaml"
    path.write_text(
        yaml.safe_dump({"defaults": {"demand_pathway": "Holistic Transition"}, "scenarios": {}})
    )
    with pytest.raises(KeyError, match="nope"):
        load_scenario("nope", path)


def test_repo_config_files_load(repo_root: Path):
    settings = load_settings(repo_root / "config" / "settings.yaml")
    assert settings.target_year == 2035
    assumptions = load_assumptions(repo_root / "config" / "assumptions.yaml")
    assert all(a.source for a in assumptions.values())
    steel = SteelSettings()
    assert steel.h2_lhv_mwh_per_t == assumptions["h2_lhv_mwh_per_t"].value
    assert steel.dri_electricity_mwh_per_t == assumptions["dri_electricity_mwh_per_t"].value
    assert steel.h2_dri_mt_steel == assumptions["h2_dri_mt_steel"].value
    # The field and the assumption row are named differently (`h2_kg_per_t` against
    # `h2_dri_kg_per_t`), which is exactly how the 51 kg/t figure went unguarded.
    assert steel.h2_kg_per_t == assumptions["h2_dri_kg_per_t"].value
    hydrogen = HydrogenSettings()
    assert hydrogen.turbine_efficiency == assumptions["hydrogen_turbine_efficiency"].value
    assert hydrogen.blue_h2_max_mw == assumptions["blue_h2_max_mw"].value
    assert hydrogen.blue_h2_cost_gbp_mwh == assumptions["blue_h2_cost_gbp_mwh"].value
    assert hydrogen.blue_h2_co2_t_per_mwh == assumptions["blue_h2_co2_t_per_mwh"].value
    assert hydrogen.blue_h2_enabled is False, (
        "the fourth blue_h2_* default is a switch, not a sourced number: blue hydrogen is off "
        "unless a scenario turns it on"
    )
    path = repo_root / "config" / "scenarios.yaml"
    names = list_scenarios(path)
    for required in [
        "test",
        "uncapped",
        "cap30",
        "cap20",
        "cap10",
        "cap5",
        "cap2",
        "cap0p5",
        "cap5_no_h2",
        "cap5_ee_demand",
        "cap5_tx_expansion",
        "cap5_import_100",
        "cap5_steel",
    ]:
        assert required in names
    # Deep-validate every scenario body, not only `test`: a typo'd or out-of-range field in any
    # of them is a pydantic error here rather than a surprise mid-sweep.
    for name in names:
        assert load_scenario(name, path).name == name
    test = load_scenario("test", repo_root / "config" / "scenarios.yaml")
    assert (
        test.snapshots is not None
        and test.snapshots.start == "2019-01-14"
        and test.snapshots.end == "2019-01-20"
    )


def test_test_scenario_overrides_solver_to_simplex(repo_root: Path):
    """PDLP's termination status is not deterministic across platforms at the one-week horizon
    (optimal on macOS ARM64, "unknown" on Linux x86_64 CI for the same inputs); the CI regression
    harness pins `test` to simplex instead. Other scenarios take the settings default (PDLP)."""
    test_scenario = load_scenario("test", repo_root / "config" / "scenarios.yaml")
    assert test_scenario.solver_options is not None
    assert test_scenario.solver_options["solver"] == "simplex"
    cap5 = load_scenario("cap5", repo_root / "config" / "scenarios.yaml")
    assert cap5.solver_options is None


def test_solver_options_merge_selects_simplex_for_test_and_pdlp_for_cap5(repo_root: Path):
    """The same deep_merge(settings.solver_options, scenario.solver_options or {}) that
    model.solve.solve() applies, exercised directly against the repo's real config."""
    settings = load_settings(repo_root / "config" / "settings.yaml")
    test_scenario = load_scenario("test", repo_root / "config" / "scenarios.yaml")
    cap5 = load_scenario("cap5", repo_root / "config" / "scenarios.yaml")
    test_options = deep_merge(dict(settings.solver_options), test_scenario.solver_options or {})
    cap5_options = deep_merge(dict(settings.solver_options), cap5.solver_options or {})
    assert test_options["solver"] == "simplex"
    assert cap5_options["solver"] == "pdlp"


def test_pumped_hydro_settings_match_assumptions(repo_root: Path):
    settings = load_settings(repo_root / "config" / "settings.yaml")
    a = load_assumptions(repo_root / "config" / "assumptions.yaml")
    assert settings.pumped_hydro_hours == a["pumped_hydro_hours"].value
    assert (
        settings.pumped_hydro_round_trip_efficiency == a["pumped_hydro_round_trip_efficiency"].value
    )
