from pathlib import Path

import pandas as pd
import pytest

from gb2035.app.data import (
    DEFAULT_SCENARIO,
    HEADLINES,
    MARKER_FILES,
    available_scenarios,
    find_project_root,
    headline_values,
    read_assumptions_table,
    read_run_meta,
    read_scenario_table,
    read_summary,
    resolve_root,
    scenario_descriptions,
)
from gb2035.results.summary import ORDER


def make_root(tmp_path: Path) -> Path:
    for rel in MARKER_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder\n")
    return tmp_path


def test_find_project_root_walks_up_from_a_nested_file(tmp_path: Path):
    root = make_root(tmp_path)
    nested = root / "src" / "gb2035" / "app"
    nested.mkdir(parents=True)
    assert find_project_root(nested / "main.py") == root


def test_find_project_root_accepts_the_root_itself(tmp_path: Path):
    root = make_root(tmp_path)
    assert find_project_root(root) == root


def test_find_project_root_needs_every_marker(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "scenarios.yaml").write_text("scenarios: {}\n")
    with pytest.raises(FileNotFoundError, match="no gb2035 project root"):
        find_project_root(tmp_path)


def test_resolve_root_prefers_an_explicit_flag(tmp_path: Path):
    root = make_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert resolve_root(["--root", str(root)], elsewhere) == root


def test_resolve_root_falls_back_to_discovery(tmp_path: Path):
    root = make_root(tmp_path)
    assert resolve_root([], root / "src" / "gb2035" / "app" / "main.py") == root


def test_the_repository_is_a_project_root(repo_root: Path):
    assert find_project_root(repo_root / "src" / "gb2035" / "app") == repo_root


def test_available_scenarios_all_have_a_summary_row(repo_root: Path):
    names = available_scenarios(repo_root)
    assert DEFAULT_SCENARIO in names
    for name in names:
        assert (repo_root / "results" / name / "summary_row.csv").exists()


def test_available_scenarios_follow_the_summary_order(repo_root: Path):
    names = available_scenarios(repo_root)
    ranked = [n for n in ORDER if n in names]
    assert names[: len(ranked)] == ranked


def test_read_summary_covers_every_available_scenario(repo_root: Path):
    summary = read_summary(repo_root)
    assert set(available_scenarios(repo_root)) <= set(summary["scenario"])
    assert "total_cost_gbp_bn_per_yr" in summary.columns


def test_read_scenario_table_reads_a_committed_csv(repo_root: Path):
    capacities = read_scenario_table(repo_root, DEFAULT_SCENARIO, "capacities")
    assert list(capacities.columns) == [
        "component",
        "name",
        "carrier",
        "zone",
        "p_nom_opt",
        "p_nom_min",
        "unit",
        "existing",
    ]


def test_read_scenario_table_names_the_missing_file(tmp_path: Path):
    root = make_root(tmp_path)
    scenario_dir = root / "results" / "solo"
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "summary_row.csv").write_text("scenario\nsolo\n")
    with pytest.raises(FileNotFoundError, match="capacities"):
        read_scenario_table(root, "solo", "capacities")


def test_read_scenario_table_rejects_an_unknown_table(repo_root: Path):
    with pytest.raises(ValueError, match="unknown result table"):
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "dispatch")


def test_read_scenario_table_rejects_an_unknown_scenario(repo_root: Path):
    with pytest.raises(ValueError, match="unknown scenario"):
        read_scenario_table(repo_root, "not-a-real-scenario", "capacities")


def test_read_scenario_table_rejects_a_traversal_scenario(repo_root: Path):
    with pytest.raises(ValueError, match="unknown scenario"):
        read_scenario_table(repo_root, "../../etc", "capacities")


def test_read_scenario_table_rejects_an_absolute_scenario(repo_root: Path):
    with pytest.raises(ValueError, match="unknown scenario"):
        read_scenario_table(repo_root, "/etc", "capacities")


def test_read_run_meta_describes_the_solve(repo_root: Path):
    meta = read_run_meta(repo_root, DEFAULT_SCENARIO)
    assert meta["scenario"] == DEFAULT_SCENARIO
    assert meta["snapshots"] > 0
    assert meta["pypsa_version"]


def test_read_run_meta_names_the_missing_file(tmp_path: Path):
    root = make_root(tmp_path)
    scenario_dir = root / "results" / "solo"
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "summary_row.csv").write_text("scenario\nsolo\n")
    with pytest.raises(FileNotFoundError, match="run_meta"):
        read_run_meta(root, "solo")


def test_read_run_meta_rejects_an_unknown_scenario(repo_root: Path):
    with pytest.raises(ValueError, match="unknown scenario"):
        read_run_meta(repo_root, "not-a-real-scenario")


def test_read_run_meta_rejects_a_traversal_scenario(repo_root: Path):
    with pytest.raises(ValueError, match="unknown scenario"):
        read_run_meta(repo_root, "../../etc")


def test_read_run_meta_rejects_an_absolute_scenario(repo_root: Path):
    with pytest.raises(ValueError, match="unknown scenario"):
        read_run_meta(repo_root, "/etc")


def test_scenario_descriptions_come_from_the_yaml(repo_root: Path):
    descriptions = scenario_descriptions(repo_root)
    assert descriptions[DEFAULT_SCENARIO]
    assert set(available_scenarios(repo_root)) <= set(descriptions)


def test_read_assumptions_table_has_a_source_for_every_row(repo_root: Path):
    table = read_assumptions_table(repo_root)
    assert list(table.columns) == ["key", "value", "unit", "confidence", "source", "note"]
    assert len(table) > 10
    assert (table["source"].str.len() > 0).all()


def test_headline_values_formats_a_summary_row():
    row = pd.Series(
        {
            "total_cost_gbp_bn_per_yr": 14.835,
            "emissions_mt": 5.0,
            "shadow_carbon_price_gbp_per_t": 52.4789,
            "net_imports_twh": 14.6393,
            "curtailed_share_wind_solar": 0.01597,
        }
    )
    assert [(label, value) for label, value, _ in headline_values(row)] == [
        ("System cost", "14.84 bn GBP/yr"),
        ("Emissions", "5.0 MtCO2/yr"),
        ("Shadow carbon price", "52 GBP/t"),
        ("Net imports", "+14.6 TWh"),
        ("Wind and solar curtailed", "1.6%"),
    ]
    assert all(note for _, _, note in headline_values(row))


def test_every_headline_column_exists_in_the_committed_summary(repo_root: Path):
    summary = read_summary(repo_root)
    assert [h.column for h in HEADLINES if h.column not in summary.columns] == []
