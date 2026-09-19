import json
from pathlib import Path

import pandas as pd
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

    costs_before = pd.read_csv(out / "costs.csv")
    total_before = float(costs_before.loc[costs_before["kind"] == "total", "gbp_per_yr"].iloc[0])
    summary_before = pd.read_csv(out / "summary_row.csv")
    bn_before = float(summary_before["total_cost_gbp_bn_per_yr"].iloc[0])

    r = runner.invoke(
        app,
        ["extract", "--scenario", "test", "--root", str(repo_root), "--results-dir", str(tmp_path)],
    )
    assert r.exit_code == 0, r.stdout
    costs_after = pd.read_csv(out / "costs.csv")
    total_after = float(costs_after.loc[costs_after["kind"] == "total", "gbp_per_yr"].iloc[0])
    summary_after = pd.read_csv(out / "summary_row.csv")
    bn_after = float(summary_after["total_cost_gbp_bn_per_yr"].iloc[0])
    assert total_after == pytest.approx(total_before, rel=1e-9)
    assert bn_after == pytest.approx(bn_before, rel=1e-9)


def test_version_accepts_root(repo_root: Path):
    r = runner.invoke(app, ["version", "--root", str(repo_root)])
    assert r.exit_code == 0
    assert "0.1.0" in r.stdout


def test_run_accepts_resolution_hours(repo_root: Path, tmp_path: Path):
    # resolution_hours=4 (not 3): under the committed HiGHS PDLP solver, resolution_hours=3 on
    # this specific one-week `test` fixture hits a HiGHS postsolve check that downgrades an
    # internally-"Optimal" PDLP solution to "Unknown" (poor RHS/bound scaling already flagged by
    # HiGHS's own presolve warnings on this short window; confirmed absent at 2, 4 and 6). This is
    # a fixture-scale numerical edge case, not a fault in --resolution-hours or in PDLP on the real
    # full-length scenarios (confirmed "optimal" for a full 3-hourly year); see task-15a-report.md.
    r = runner.invoke(
        app,
        [
            "run",
            "--scenario",
            "test",
            "--resolution-hours",
            "4",
            "--root",
            str(repo_root),
            "--results-dir",
            str(tmp_path),
        ],
    )
    assert r.exit_code == 0, r.stdout
    meta = json.loads((tmp_path / "test" / "run_meta.json").read_text())
    assert meta["snapshots"] == 42
    assert meta["resolution_hours"] == 4


def test_run_rejects_resolution_hours_out_of_range(repo_root: Path, tmp_path: Path):
    r = runner.invoke(
        app,
        [
            "run",
            "--scenario",
            "test",
            "--resolution-hours",
            "0",
            "--root",
            str(repo_root),
            "--results-dir",
            str(tmp_path),
        ],
    )
    assert r.exit_code != 0
    assert not (tmp_path / "test" / "run_meta.json").exists()


def test_unknown_scenario_fails_cleanly(repo_root: Path, tmp_path: Path):
    r = runner.invoke(
        app, ["run", "--scenario", "nope", "--root", str(repo_root), "--results-dir", str(tmp_path)]
    )
    assert r.exit_code != 0
    assert "unknown scenario" in (r.stdout + str(r.exception))
