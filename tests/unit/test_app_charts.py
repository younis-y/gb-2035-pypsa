import subprocess
import sys
from pathlib import Path

import pandas as pd

from gb2035.app import palette
from gb2035.app.charts import (
    cap_scenarios,
    capacity_mix_figure,
    cost_and_shadow_price_figure,
    energy_mix_figure,
)
from gb2035.app.data import DEFAULT_SCENARIO, read_scenario_table, read_summary
from gb2035.report import figures


def test_palette_matches_the_readme_figures():
    """One palette, two renderers. These copies must never drift."""
    assert list(palette.TECH_SERIES) == figures.TECH_COLS
    assert list(palette.CAP_ORDER) == figures.CAP_ORDER
    assert (palette.SURFACE, palette.INK_PRIMARY, palette.GRIDLINE, palette.BASELINE) == (
        figures.SURFACE,
        figures.INK_PRIMARY,
        figures.GRIDLINE,
        figures.BASELINE,
    )


def test_every_committed_carrier_has_a_colour(repo_root: Path):
    energy = read_scenario_table(repo_root, DEFAULT_SCENARIO, "energy")
    missing = [c for c in energy["carrier"] if c not in palette.CARRIER_COLOURS]
    assert missing == []


def test_cap_scenarios_orders_by_emissions(repo_root: Path):
    df = cap_scenarios(read_summary(repo_root))
    assert set(df["scenario"]) <= set(palette.CAP_ORDER)
    assert df["emissions_mt"].is_monotonic_decreasing


def test_cost_and_shadow_price_highlights_the_chosen_scenario(repo_root: Path):
    summary = read_summary(repo_root)
    fig = cost_and_shadow_price_figure(summary, DEFAULT_SCENARIO)
    assert len(fig.data) == 4
    assert fig.layout.xaxis.autorange == "reversed"
    plain = cost_and_shadow_price_figure(summary, "cap5_no_h2")
    assert len(plain.data) == 2, "a non-sweep scenario has nothing to highlight"


def test_capacity_mix_stacks_one_trace_per_technology(repo_root: Path):
    fig = capacity_mix_figure(read_summary(repo_root))
    assert len(fig.data) == len(palette.TECH_SERIES)
    assert fig.layout.barmode == "stack"
    assert [trace.name for trace in fig.data] == [label for _, label, _ in palette.TECH_SERIES]


def test_energy_mix_shows_electricity_only(repo_root: Path):
    energy = read_scenario_table(repo_root, DEFAULT_SCENARIO, "energy")
    fig = energy_mix_figure(energy, DEFAULT_SCENARIO)
    assert len(fig.data) == 1
    shown = set(fig.data[0].x)
    assert "blue_h2" not in shown, "hydrogen rows are not electricity and must not be plotted"
    assert shown == set(energy.loc[energy["bus_carrier"] == "AC", "carrier"])


def test_energy_mix_handles_a_scenario_with_no_hydrogen_rows():
    energy = pd.DataFrame(
        {"carrier": ["onwind", "solar"], "bus_carrier": ["AC", "AC"], "twh": [113.7, 101.6]}
    )
    fig = energy_mix_figure(energy, "synthetic")
    assert list(fig.data[0].x) == ["onwind", "solar"]


def test_gb2035_palette_never_imports_matplotlib_or_streamlit():
    """`gb2035.palette` backs both the matplotlib report and this Plotly app, so it must not
    itself pull in either rendering stack: `report/figures.py` switches the matplotlib backend
    as an import-time side effect (controller decision F1), which a shared constants module used
    by the app has no business doing.
    """
    code = (
        "import sys; import gb2035.palette; "
        "print(sorted(m for m in ('matplotlib', 'streamlit') if m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", result.stdout
