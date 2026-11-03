"""Streamlit entry point for the GB 2035 results explorer.

Run it with `gb2035 app`, or directly:
`uv run streamlit run src/gb2035/app/main.py -- --root .`

Every number on every view is read from a committed file. The app never builds or solves a
network, so it starts in seconds and works from a fresh clone or inside the container.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from gb2035.app import charts, mapview
from gb2035.app.data import (
    DEFAULT_SCENARIO,
    MAP_METRICS,
    available_scenarios,
    corridor_flows,
    headline_values,
    load_assumptions_table,
    load_bus_coordinates,
    load_run_meta,
    load_scenario_table,
    load_summary,
    load_zone_geojson,
    resolve_root,
    scenario_descriptions,
    zone_metrics,
)

st.set_page_config(page_title="GB 2035 power system explorer", layout="wide")


def overview(root: Path, scenario: str, description: str) -> None:
    summary = load_summary(root)
    row = summary[summary["scenario"] == scenario].iloc[0]
    st.subheader(f"{scenario}: headline results")
    st.caption(description or "No description in config/scenarios.yaml.")
    values = headline_values(row)
    for column, (label, value, note) in zip(st.columns(len(values)), values, strict=True):
        column.metric(label, value, help=note)
    st.plotly_chart(charts.cost_and_shadow_price_figure(summary, scenario))
    st.caption(
        "Source: results/summary.csv, cap-sweep scenarios only, ordered by realised emissions. "
        "The uncapped run prices carbon instead of capping it, so it has no dual."
    )
    meta = load_run_meta(root, scenario)
    st.caption(
        f"Solved with PyPSA {meta['pypsa_version']} at commit {meta['git_sha']}: "
        f"{meta['snapshots']} snapshots at {meta['resolution_hours']}-hourly resolution, "
        f"{meta['solver']} in {meta['solve_seconds']:.0f} s."
    )


def zone_map(root: Path, scenario: str) -> None:
    st.subheader(f"{scenario}: zones and corridors")
    label = st.selectbox("Colour zones by", list(MAP_METRICS), key="map_metric")
    metric = MAP_METRICS[label]
    metrics = zone_metrics(
        load_scenario_table(root, scenario, "capacities"),
        load_scenario_table(root, scenario, "duals"),
    )
    flows = corridor_flows(load_scenario_table(root, scenario, "flows"), load_bus_coordinates(root))
    st.plotly_chart(
        mapview.zone_choropleth(
            load_zone_geojson(root),
            metrics,
            flows,
            metric=metric.column,
            metric_label=label,
            hover_unit=metric.unit,
        )
    )
    st.caption(
        f"Zone colour from results/{scenario}/capacities.csv and duals.csv; corridor lines "
        f"from results/{scenario}/flows.csv, width scaled by net annual energy; polygons from "
        "data/derived/zones.geojson. Interconnector legs are excluded from zone capacity "
        "because capacities.csv lists both legs at full capacity. Curtailment is not extracted "
        "per zone: the system-wide split by carrier is on the Capacity and energy view."
    )
    st.dataframe(metrics, hide_index=True)


def capacity_and_energy(root: Path, scenario: str) -> None:
    st.subheader("Capacity across the cap sweep")
    st.plotly_chart(charts.capacity_mix_figure(load_summary(root)))
    st.caption("Source: results/summary.csv.")
    st.subheader(f"{scenario}: annual electricity by carrier")
    st.plotly_chart(
        charts.energy_mix_figure(load_scenario_table(root, scenario, "energy"), scenario)
    )
    st.caption(
        f"Source: results/{scenario}/energy.csv, electricity rows only. Exports and "
        "electrolysis are withdrawals and plot negative; hydrogen rows are measured in "
        "hydrogen and are not shown here."
    )
    st.subheader("Curtailment")
    st.dataframe(load_scenario_table(root, scenario, "curtailment"), hide_index=True)
    st.caption(f"Source: results/{scenario}/curtailment.csv, whole system by carrier.")


def hydrogen(root: Path, scenario: str) -> None:
    st.subheader(f"{scenario}: Teesside hydrogen")
    st.dataframe(load_scenario_table(root, scenario, "hydrogen"), hide_index=True)
    st.caption(f"Source: results/{scenario}/hydrogen.csv.")
    figure = root / "docs" / "figures" / "teesside_hydrogen.png"
    if figure.exists():
        st.image(str(figure))
        st.caption("docs/figures/teesside_hydrogen.png, written by `gb2035 report`.")


def assumptions(root: Path) -> None:
    st.subheader("Sourced assumptions")
    table = load_assumptions_table(root)
    query = st.text_input("Filter assumptions", key="assumption_filter")
    shown = table
    if query:
        mask = table.apply(
            lambda row: query.lower() in " ".join(str(v) for v in row).lower(), axis=1
        )
        shown = table[mask]
    st.dataframe(shown, hide_index=True)
    st.caption(
        "Source: config/assumptions.yaml. Every row carries a source URL and a confidence tag: "
        "published, derived or assumption. Technology capex and efficiencies live in "
        "data/derived/costs_2035_gb.csv."
    )


root = resolve_root(sys.argv[1:], Path(__file__).resolve())
scenarios = available_scenarios(root)
descriptions = scenario_descriptions(root)

st.sidebar.title("GB 2035")
st.sidebar.caption("Least-cost GB power system in 2035 under tightening CO2 caps.")
selected = st.sidebar.selectbox(
    "Scenario",
    scenarios,
    index=scenarios.index(DEFAULT_SCENARIO) if DEFAULT_SCENARIO in scenarios else 0,
    key="scenario",
)
st.sidebar.caption(f"Reading committed results from {root}.")

tabs = st.tabs(["Overview", "Map", "Capacity and energy", "Teesside hydrogen", "Assumptions"])
with tabs[0]:
    overview(root, selected, descriptions.get(selected, ""))
with tabs[1]:
    zone_map(root, selected)
with tabs[2]:
    capacity_and_energy(root, selected)
with tabs[3]:
    hydrogen(root, selected)
with tabs[4]:
    assumptions(root)
