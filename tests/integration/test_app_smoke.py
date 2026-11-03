from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from gb2035.app.data import DEFAULT_SCENARIO, MAP_METRICS, headline_values

APP = Path("src") / "gb2035" / "app" / "main.py"
TAB_LABELS = ["Overview", "Map", "Capacity and energy", "Teesside hydrogen", "Assumptions"]


def start(repo_root: Path) -> AppTest:
    at = AppTest.from_file(str(repo_root / APP), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture(scope="module")
def app(repo_root: Path) -> AppTest:
    return start(repo_root)


def test_every_view_renders(app: AppTest):
    assert [tab.label for tab in app.tabs] == TAB_LABELS
    assert app.sidebar.selectbox[0].label == "Scenario"
    assert len(app.get("plotly_chart")) >= 3, "cost, capacity, energy and the map"
    assert len(app.dataframe) >= 4, "zone metrics, curtailment, hydrogen, assumptions"


def test_overview_metrics_come_from_summary_csv(app: AppTest, repo_root: Path):
    summary = pd.read_csv(repo_root / "results" / "summary.csv").set_index("scenario")
    expected = [
        (label, value) for label, value, _ in headline_values(summary.loc[DEFAULT_SCENARIO])
    ]
    assert [(m.label, m.value) for m in app.metric] == expected


def test_map_view_offers_every_metric(app: AppTest):
    selector = app.main.selectbox[0]
    assert selector.label == "Colour zones by"
    assert list(selector.options) == list(MAP_METRICS)


def test_switching_scenario_moves_every_headline(repo_root: Path):
    summary = pd.read_csv(repo_root / "results" / "summary.csv").set_index("scenario")
    at = start(repo_root)
    at.sidebar.selectbox[0].select("cap2").run()
    assert not at.exception, at.exception
    expected = [(label, value) for label, value, _ in headline_values(summary.loc["cap2"])]
    assert [(m.label, m.value) for m in at.metric] == expected


def test_assumptions_view_lists_every_sourced_number(app: AppTest, repo_root: Path):
    import yaml

    expected = yaml.safe_load((repo_root / "config" / "assumptions.yaml").read_text())
    tables = [df for df in (frame.value for frame in app.dataframe) if "source" in df.columns]
    assert len(tables) == 1
    assert len(tables[0]) == len(expected)
