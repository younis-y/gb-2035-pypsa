import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gb2035.cli import app

runner = CliRunner()
pytestmark = pytest.mark.slow


def test_scenarios_and_config_show(repo_root: Path):
    r = runner.invoke(app, ["scenarios", "--root", str(repo_root)])
    assert r.exit_code == 0 and "cap5_no_h2" in r.stdout
    r = runner.invoke(app, ["config-show", "--scenario", "cap5", "--root", str(repo_root)])
    assert r.exit_code == 0 and "co2_cap_mt" in r.stdout


def test_run_test_scenario_end_to_end(repo_root: Path, tmp_path: Path):
    r = runner.invoke(
        app, ["run", "--scenario", "test", "--root", str(repo_root), "--results-dir", str(tmp_path)]
    )
    assert r.exit_code == 0, r.stdout
    out = tmp_path / "test"
    for name in [
        "capacities.csv",
        "energy.csv",
        "emissions.csv",
        "costs.csv",
        "duals.csv",
        "flows.csv",
        "curtailment.csv",
        "hydrogen.csv",
        "summary_row.csv",
        "dispatch_hourly.parquet",
        "network.nc",
        "run_meta.json",
    ]:
        assert (out / name).exists(), name
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["scenario"] == "test" and meta["snapshots"] == 168 and meta["solve_seconds"] > 0
    r = runner.invoke(app, ["report", "--root", str(repo_root), "--results-dir", str(tmp_path)])
    assert r.exit_code == 0
    assert (tmp_path / "summary.csv").exists()


def test_unknown_scenario_fails_cleanly(repo_root: Path, tmp_path: Path):
    r = runner.invoke(
        app, ["run", "--scenario", "nope", "--root", str(repo_root), "--results-dir", str(tmp_path)]
    )
    assert r.exit_code != 0
    assert "unknown scenario" in (r.stdout + str(r.exception))
