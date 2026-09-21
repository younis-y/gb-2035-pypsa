from pathlib import Path

import pandas as pd

from gb2035.app.data import (
    DEFAULT_SCENARIO,
    MAP_METRICS,
    corridor_flows,
    read_bus_coordinates,
    read_scenario_table,
    read_zone_geojson,
    zone_metrics,
)
from gb2035.data.zones import LAND_ZONES, OFFSHORE_ZONES


def test_zone_geojson_keys_every_zone_on_name_1(repo_root: Path):
    geojson = read_zone_geojson(repo_root)
    names = [feature["properties"]["Name_1"] for feature in geojson["features"]]
    assert set(names) == set(LAND_ZONES) | set(OFFSHORE_ZONES)
    assert len(names) == 23


def test_bus_coordinates_cover_every_land_zone(repo_root: Path):
    buses = read_bus_coordinates(repo_root)
    assert set(buses["name"]) == set(LAND_ZONES)
    assert buses["y"].between(49.0, 61.0).all()
    assert buses["x"].between(-8.0, 2.0).all()


def test_zone_metrics_has_one_row_per_land_zone(repo_root: Path):
    metrics = zone_metrics(
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "capacities"),
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "duals"),
    )
    assert list(metrics["zone"]) == list(LAND_ZONES)
    assert (metrics["new_build_gw"] <= metrics["total_capacity_gw"] + 1e-9).all()
    assert metrics["price_gbp_per_mwh"].notna().all()
    assert metrics["zone_name"].str.len().gt(0).all()


def test_zone_metrics_drops_interconnector_legs_and_hydrogen():
    capacities = pd.DataFrame(
        {
            "component": ["Generator", "Generator", "Generator", "StorageUnit", "Link"],
            "name": [
                "onwind Z7",
                "ic NSL import",
                "blue_h2 Teesside",
                "battery Z7",
                "electrolysis",
            ],
            "carrier": ["onwind", "import", "blue_h2", "battery", "electrolysis"],
            "zone": ["Z7", "Z7", "Teesside", "Z7", "Z7->Teesside H2"],
            "p_nom_opt": [1000.0, 1686.96, 1200.0, 500.0, 900.0],
            "p_nom_min": [0.0, 0.0, 0.0, 0.0, 0.0],
            "unit": ["MW"] * 5,
            "existing": [False, True, True, False, False],
        }
    )
    duals = pd.DataFrame(
        {
            "metric": ["shadow_carbon_price_gbp_per_t", "demand_weighted_price_gbp_per_mwh"],
            "zone": ["GB", "Z7"],
            "value": [52.0, 61.0],
        }
    )
    metrics = zone_metrics(capacities, duals).set_index("zone")
    assert metrics.loc["Z7", "total_capacity_gw"] == 1.5
    assert metrics.loc["Z7", "new_build_gw"] == 1.5
    assert metrics.loc["Z7", "price_gbp_per_mwh"] == 61.0
    assert metrics.loc["Z8", "total_capacity_gw"] == 0.0


def test_zone_metrics_reads_a_string_existing_column():
    """`existing` is bool in the committed CSVs; a string column must not read as all-True."""
    capacities = pd.DataFrame(
        {
            "component": ["Generator", "Generator"],
            "name": ["onwind Z7", "onwind_existing Z7"],
            "carrier": ["onwind", "onwind"],
            "zone": ["Z7", "Z7"],
            "p_nom_opt": [1000.0, 3000.0],
            "p_nom_min": [0.0, 3000.0],
            "unit": ["MW", "MW"],
            "existing": ["False", "True"],
        }
    )
    duals = pd.DataFrame({"metric": [], "zone": [], "value": []})
    metrics = zone_metrics(capacities, duals).set_index("zone")
    assert metrics.loc["Z7", "new_build_gw"] == 1.0
    assert metrics.loc["Z7", "total_capacity_gw"] == 4.0


def test_corridor_flows_places_every_corridor_between_two_buses(repo_root: Path):
    flows = read_scenario_table(repo_root, DEFAULT_SCENARIO, "flows")
    corridors = corridor_flows(flows, read_bus_coordinates(repo_root))
    assert len(corridors) == len(flows)
    assert corridors[["lon0", "lat0", "lon1", "lat1", "lon_mid", "lat_mid"]].notna().all().all()
    first = corridors.iloc[0]
    assert first["net_twh"] == first["twh_forward"] - first["twh_reverse"]
    assert first["label"] == f"{first['bus0']} to {first['bus1']}"


def test_map_metrics_columns_exist_in_zone_metrics(repo_root: Path):
    metrics = zone_metrics(
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "capacities"),
        read_scenario_table(repo_root, DEFAULT_SCENARIO, "duals"),
    )
    assert len(MAP_METRICS) == 3
    for metric in MAP_METRICS.values():
        assert metric.column in metrics.columns
        assert metric.unit
