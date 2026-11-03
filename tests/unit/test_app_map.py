from pathlib import Path

import pandas as pd
import pytest

from gb2035.app.data import (
    DEFAULT_SCENARIO,
    MAP_METRICS,
    corridor_flows,
    read_bus_coordinates,
    read_scenario_table,
    read_zone_geojson,
    zone_metrics,
)
from gb2035.app.mapview import TEESSIDE_LATLON, line_widths, zone_choropleth
from gb2035.data.zones import OFFSHORE_ZONES


@pytest.fixture(scope="module")
def pieces(repo_root: Path):
    metrics = zone_metrics(
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "capacities"),
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "duals"),
    )
    flows = corridor_flows(
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "flows"), read_bus_coordinates(repo_root)
    )
    return read_zone_geojson(repo_root), metrics, flows


def build(pieces, metric_label: str = "New-build capacity (GW)"):
    geojson, metrics, flows = pieces
    metric = MAP_METRICS[metric_label]
    return zone_choropleth(
        geojson,
        metrics,
        flows,
        metric=metric.column,
        metric_label=metric_label,
        hover_unit=metric.unit,
    )


def test_line_widths_scale_between_one_and_six():
    widths = line_widths(pd.Series([0.0, 5.0, -10.0]))
    assert widths.tolist() == [1.0, 3.5, 6.0]


def test_line_widths_survive_an_all_zero_column():
    assert line_widths(pd.Series([0.0, 0.0])).tolist() == [1.5, 1.5]


def test_map_has_a_trace_per_corridor_plus_four(pieces):
    _, _, flows = pieces
    fig = build(pieces)
    assert len(fig.data) == len(flows) + 4


def test_map_colours_land_zones_from_the_chosen_metric(pieces):
    _, metrics, _ = pieces
    fig = build(pieces, "Demand-weighted price (GBP/MWh)")
    choropleth = fig.data[0]
    assert list(choropleth.locations) == list(metrics["zone"])
    assert list(choropleth.z) == list(metrics["price_gbp_per_mwh"])
    assert choropleth.featureidkey == "properties.Name_1"


def test_map_outlines_the_offshore_lease_zones(pieces):
    fig = build(pieces)
    assert set(fig.data[1].locations) == set(OFFSHORE_ZONES)
    assert fig.data[1].showscale is False


def test_map_marks_teesside_and_needs_no_token(pieces):
    fig = build(pieces)
    teesside = fig.data[-1]
    assert (teesside.lat[0], teesside.lon[0]) == TEESSIDE_LATLON
    assert fig.layout.map.style == "open-street-map"
    assert "mapbox" not in fig.to_plotly_json()["layout"]


def test_map_accepts_a_tile_free_style_for_static_export(pieces):
    geojson, metrics, flows = pieces
    fig = zone_choropleth(
        geojson,
        metrics,
        flows,
        metric="new_build_gw",
        metric_label="New-build capacity (GW)",
        hover_unit="GW",
        map_style="white-bg",
    )
    assert fig.layout.map.style == "white-bg"
