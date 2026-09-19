from pathlib import Path

import pandas as pd

from gb2035.report.figures import make_figures, optimised_vs_fes
from gb2035.report.readme import summary_markdown, update_readme


def test_summary_markdown_has_one_row_per_scenario():
    df = pd.DataFrame(
        {
            "scenario": ["cap5", "cap2"],
            "total_cost_gbp_bn_per_yr": [40.123, 45.6],
            "shadow_carbon_price_gbp_per_t": [120.0, 300.5],
            "emissions_mt": [5.0, 2.0],
            "onwind_gw": [40.0, 45.0],
            "offwind_gw": [70.0, 90.0],
            "solar_gw": [60.0, 70.0],
            "battery_gw": [20.0, 30.0],
            "electrolysis_gw": [2.0, 3.0],
            "teesside_green_h2_twh": [4.0, 5.0],
            "teesside_blue_h2_twh": [1.0, 0.0],
        }
    )
    md = summary_markdown(df)
    assert md.count("\n| cap") == 2
    assert "40.1" in md and "300" in md


def test_update_readme_replaces_block(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("# T\n\n<!-- summary:start -->\nold\n<!-- summary:end -->\n\ntail\n")
    update_readme(readme, "| a |\n|---|\n| 1 |")
    text = readme.read_text()
    assert "old" not in text and "| 1 |" in text and text.endswith("tail\n")


def test_make_figures_writes_five_pngs(tmp_path: Path):
    """`make_figures` on a two-row synthetic summary produces all five README figures.

    Covers every `summary_row.csv` column (see task-15-brief context) plus the `*_new_gw`
    greenfield columns `optimised_vs_fes` overlays per controller decision 1, and a minimal
    FES frame carrying the six metrics `optimised_vs_fes` reads.
    """
    summary = pd.DataFrame(
        {
            "scenario": ["cap5", "cap2"],
            "total_cost_gbp_bn_per_yr": [40.1, 45.6],
            "lp_objective_gbp_bn_per_yr": [38.0, 43.2],
            "fixed_asset_cost_gbp_bn_per_yr": [2.1, 2.4],
            "shadow_carbon_price_gbp_per_t": [120.0, 300.5],
            "emissions_mt": [5.0, 2.0],
            "onwind_gw": [40.0, 45.0],
            "offwind_gw": [70.0, 90.0],
            "solar_gw": [60.0, 70.0],
            "gas_gw": [10.0, 4.0],
            "gas_ccs_gw": [6.0, 9.0],
            "nuclear_gw": [4.46, 4.46],
            "battery_gw": [20.0, 30.0],
            "electrolysis_gw": [2.0, 3.0],
            "h2_store_gwh": [120.0, 180.0],
            "h2_turbine_gw_el": [3.0, 4.5],
            "teesside_green_h2_twh": [4.0, 5.0],
            "teesside_blue_h2_twh": [1.0, 0.0],
            "curtailed_share_wind_solar": [0.02, 0.035],
            "onwind_new_gw": [8.0, 11.0],
            "offwind_new_gw": [48.0, 63.0],
            "solar_new_gw": [52.0, 61.0],
            "battery_new_gw": [20.0, 30.0],
        }
    )
    fes = pd.DataFrame(
        {
            "metric": [
                "offshore_wind_gw",
                "onshore_wind_gw",
                "solar_gw",
                "battery_gw",
                "gas_ccus_gw",
                "unabated_gas_gw",
            ],
            "pathway": ["Holistic Transition"] * 6,
            "value": [85.0, 30.0, 65.0, 25.0, 6.0, 4.0],
        }
    )
    out_dir = tmp_path / "figures"
    paths = make_figures(summary, tmp_path, fes, out_dir)
    assert len(paths) == 5
    for path in paths:
        assert path.exists()
        assert path.stat().st_size > 0


def test_make_figures_falls_back_when_default_fes_scenario_missing(tmp_path: Path):
    """Mid-sweep, `cap2` (the default `optimised_vs_fes` comparison scenario) may not have been
    solved yet. `make_figures` must not raise `IndexError` in that case: it should fall back to
    the tightest cap scenario actually present (`cap5` here) and still return every figure it
    could draw, rather than aborting the whole report after summary.csv is already written.
    """
    summary = pd.DataFrame(
        {
            "scenario": ["cap5"],
            "total_cost_gbp_bn_per_yr": [40.1],
            "lp_objective_gbp_bn_per_yr": [38.0],
            "fixed_asset_cost_gbp_bn_per_yr": [2.1],
            "shadow_carbon_price_gbp_per_t": [120.0],
            "emissions_mt": [5.0],
            "onwind_gw": [40.0],
            "offwind_gw": [70.0],
            "solar_gw": [60.0],
            "gas_gw": [10.0],
            "gas_ccs_gw": [6.0],
            "nuclear_gw": [4.46],
            "battery_gw": [20.0],
            "electrolysis_gw": [2.0],
            "h2_store_gwh": [120.0],
            "h2_turbine_gw_el": [3.0],
            "teesside_green_h2_twh": [4.0],
            "teesside_blue_h2_twh": [1.0],
            "curtailed_share_wind_solar": [0.02],
            "onwind_new_gw": [8.0],
            "offwind_new_gw": [48.0],
            "solar_new_gw": [52.0],
            "battery_new_gw": [20.0],
        }
    )
    fes = pd.DataFrame(
        {
            "metric": [
                "offshore_wind_gw",
                "onshore_wind_gw",
                "solar_gw",
                "battery_gw",
                "gas_ccus_gw",
                "unabated_gas_gw",
            ],
            "pathway": ["Holistic Transition"] * 6,
            "value": [85.0, 30.0, 65.0, 25.0, 6.0, 4.0],
        }
    )
    out_dir = tmp_path / "figures"
    paths = make_figures(summary, tmp_path, fes, out_dir)
    # cap5 is the only (so tightest) cap scenario present: optimised_vs_fes falls back to it
    # instead of raising, and every one of the five figures still renders.
    assert len(paths) == 5
    for path in paths:
        assert path.exists()
        assert path.stat().st_size > 0


def test_optimised_vs_fes_returns_none_when_no_cap_scenario_present(tmp_path: Path):
    """When none of `CAP_ORDER`'s scenarios have been solved yet, there is nothing to compare
    against FES: `optimised_vs_fes` should return `None` (and `make_figures` skips it) rather
    than raising `IndexError` on an empty `scenario == ...` selection."""
    summary = pd.DataFrame({"scenario": ["cap5_no_h2"]})
    fes = pd.DataFrame({"metric": [], "pathway": [], "value": []})
    assert optimised_vs_fes(summary, fes, tmp_path) is None
