"""Streamlit entry point for the GB 2035 results explorer.

Run it with `gb2035 app`, or directly:
`uv run streamlit run src/gb2035/app/main.py -- --root .`

Every number on every view is read from a committed file. The app never builds or solves a
network, so it starts in seconds and works from a fresh clone or inside the container.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st

from gb2035.app import charts, mapview
from gb2035.app.data import (
    DEFAULT_SCENARIO,
    HEADLINES,
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

# The brand mark, a pylon, drawn from CSS: st.html strips inline SVG.
PYLON_ICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
    "fill='none' stroke='%237FAEFF' stroke-width='1.7' stroke-linecap='round' "
    "stroke-linejoin='round'%3E%3Cpath d='M12 2 7 22M12 2l5 20M5 7h14M6.5 12h11M9 7l6 5"
    "M15 7l-6 5M8 17l8-5M16 17l-8-5'/%3E%3C/svg%3E"
)

# The Spend Engineer layout on top of the graphite theme in .streamlit/config.toml: flat panels
# with one hairline, pill navigation, status colours that always come with a word.
STYLE = """<style>
.block-container{max-width:1500px;padding-top:2.2rem}
h1,h2,h3{letter-spacing:-.02em}
[data-testid="stMetric"]{background:#25282E;border:1px solid rgba(255,255,255,.09);
 border-radius:16px;padding:14px 16px 10px;box-shadow:0 10px 28px rgba(0,0,0,.24)}
[data-testid="stMetricLabel"]{min-height:2.7em;align-items:flex-start}
[data-testid="stMetricLabel"] *{white-space:normal!important;overflow:visible!important;
 text-overflow:clip!important}
[data-testid="stMetricLabel"] p{font-size:13.5px;font-weight:600;color:#F2F4F7;line-height:1.35}
[data-testid="stMetricChart"] svg{background-color:transparent!important}
[data-testid="stMetricChart"] .mark-line path{stroke:#7FAEFF!important}
[data-testid="stMetricValue"]{font-size:26px;font-weight:700;letter-spacing:-.02em;
 font-variant-numeric:tabular-nums}
[role="tablist"]{gap:6px;border:0!important;box-shadow:none!important}
[role="tablist"]::before,[role="tablist"]::after{display:none!important}
[data-testid="stTab"]{padding:8px 14px!important;border-radius:12px;
 border:1px solid transparent!important}
[data-testid="stTab"] p{color:#A3ACB9;font-weight:600}
[data-testid="stTab"]:hover{background:#2E333B}
[data-testid="stTab"]::before,[data-testid="stTab"]::after{display:none!important}
[data-testid="stTab"]{box-shadow:none!important;border-bottom-width:1px!important}
[data-testid="stTab"][aria-selected="true"]{background:rgba(37,99,235,.16);
 border-color:rgba(127,174,255,.35)!important}
[data-testid="stTab"][aria-selected="true"] p{color:#F2F4F7}
.stSkillsNudge,.modebar-container{display:none!important}
[data-testid="stPlotlyChart"]{border:1px solid rgba(255,255,255,.09);
 border-radius:16px;overflow:hidden;box-shadow:0 10px 28px rgba(0,0,0,.24)}
[data-testid="stCaptionContainer"]{color:#8E98A8}
.brand{display:flex;gap:12px;align-items:center;margin-bottom:8px}
.mark{width:36px;height:36px;flex:none;border-radius:11px;border:1px solid rgba(255,255,255,.1);
 background:#2B2F36 center/18px no-repeat url("PYLON_ICON")}
.brand b{display:block;font-size:16px;letter-spacing:-.01em}
.brand small{color:#A3ACB9;font-size:12.5px}
.sec{font-size:11.5px;font-weight:700;letter-spacing:.08em;color:#8E98A8;margin:8px 0 2px}
.pipe{list-style:none;margin:0;padding:0}
.pipe li{position:relative;display:flex;justify-content:space-between;gap:8px;
 padding:6px 0 6px 18px;font-size:13px;color:#A3ACB9}
.pipe li b{color:#F2F4F7;font-variant-numeric:tabular-nums}
.pipe li::before{content:"";position:absolute;left:0;top:12px;width:8px;height:8px;
 border-radius:50%;background:#7FAEFF}
.pipe li::after{content:"";position:absolute;left:3.5px;top:22px;bottom:-12px;width:1px;
 background:rgba(255,255,255,.07)}
.pipe li:last-child::after{display:none}
.pipe li.ok::before{background:#6CC28A}.pipe li.ok b{color:#6CC28A}
.foot{display:grid;gap:6px;padding-top:12px;border-top:1px solid rgba(255,255,255,.07);
 font-size:12.5px;color:#A3ACB9}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#6CC28A;
 margin-right:8px}
.head h1{font-size:26px;line-height:1.2;display:flex;align-items:center;gap:10px;padding:0}
.chip{display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;
 font-size:12.5px;font-weight:600;letter-spacing:0;background:rgba(37,99,235,.16);color:#7FAEFF}
.ledger{font-size:13px;color:#A3ACB9;margin-top:6px}.ledger b{color:#F2F4F7;margin-right:6px}
</style>""".replace("PYLON_ICON", PYLON_ICON)

BRAND = (
    '<div class="brand"><div class="mark"></div><div><b>GB 2035</b>'
    "<small>Power system · results explorer</small></div></div>"
    '<div class="sec">SCENARIO</div>'
)


def pipeline_panel(meta: dict[str, object]) -> str:
    """The "how we got here" steps, read from the scenario's run_meta.json."""
    steps = [
        ("Snapshots", f"{meta['snapshots']:,}"),
        ("Resolution", f"{meta['resolution_hours']}-hourly"),
        ("Solver", str(meta["solver"])),
        ("Solve time", f"{float(str(meta['solve_seconds'])):.0f} s"),
        ("Committed at", str(meta["git_sha"])),
    ]
    rows = "".join(
        f'<li class="{"ok" if i == len(steps) - 1 else ""}"><span>{escape(k)}</span>'
        f"<b>{escape(v)}</b></li>"
        for i, (k, v) in enumerate(steps)
    )
    return (
        f'<div class="sec">HOW WE GOT HERE</div><ol class="pipe">{rows}</ol>'
        '<div class="foot"><div><span class="dot"></span>Committed results, nothing solved here'
        f'</div><div><span class="dot" style="background:#7FAEFF"></span>PyPSA '
        f"{escape(str(meta['pypsa_version']))}</div></div>"
    )


def headline_tiles(root: Path, scenario: str) -> None:
    """The five headline numbers as tiles, each with its sparkline across the cap sweep."""
    summary = load_summary(root)
    row = summary[summary["scenario"] == scenario].iloc[0]
    sweep = charts.cap_scenarios(summary)
    values = headline_values(row)
    for column, headline, (label, value, note) in zip(
        st.columns(len(values)), HEADLINES, values, strict=True
    ):
        column.metric(label, value, help=note, chart_data=sweep[headline.column].tolist())
    st.caption("Sparklines: the cap sweep from results/summary.csv, highest emissions first.")


def overview(root: Path, scenario: str) -> None:
    st.subheader("Cost and carbon price across the sweep")
    st.plotly_chart(charts.cost_and_shadow_price_figure(load_summary(root), scenario))
    st.caption(
        f"Source: results/summary.csv, cap-sweep scenarios only, ordered by realised emissions; "
        f"{scenario} is ringed. The uncapped run prices carbon instead of capping it, so it has "
        "no dual."
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
    left, right = st.columns([5, 4])
    left.plotly_chart(
        mapview.zone_choropleth(
            load_zone_geojson(root),
            metrics,
            flows,
            metric=metric.column,
            metric_label=label,
        )
    )
    right.dataframe(
        metrics,
        hide_index=True,
        height="content",
        column_order=("zone_name", "new_build_gw", "total_capacity_gw", "price_gbp_per_mwh"),
        column_config={
            "zone_name": "Zone",
            "new_build_gw": st.column_config.NumberColumn("New GW", format="%.2f", width="small"),
            "total_capacity_gw": st.column_config.NumberColumn(
                "Total GW", format="%.2f", width="small"
            ),
            "price_gbp_per_mwh": st.column_config.NumberColumn(
                "GBP/MWh", format="%.2f", width="small"
            ),
        },
    )
    st.caption(
        f"Zone colour from results/{scenario}/capacities.csv and duals.csv; corridor lines "
        f"from results/{scenario}/flows.csv, width scaled by net annual energy; polygons from "
        "data/derived/zones.geojson. Interconnector legs are excluded from zone capacity "
        "because capacities.csv lists both legs at full capacity. Curtailment is not extracted "
        "per zone: the system-wide split by carrier is on the Capacity and energy view."
    )


def capacity_and_energy(root: Path, scenario: str) -> None:
    st.subheader("Capacity across the cap sweep")
    st.plotly_chart(charts.capacity_mix_figure(load_summary(root)))
    st.caption("Source: results/summary.csv, ordered by realised emissions, highest first.")
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
    st.subheader("Green and blue hydrogen across the cap sweep")
    st.plotly_chart(charts.hydrogen_supply_figure(load_summary(root)))
    st.caption("Source: results/summary.csv, ordered by realised emissions, highest first.")


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

st.html(STYLE)
st.sidebar.html(BRAND)
selected = st.sidebar.selectbox(
    "Scenario",
    scenarios,
    index=scenarios.index(DEFAULT_SCENARIO) if DEFAULT_SCENARIO in scenarios else 0,
    key="scenario",
    label_visibility="collapsed",
)
meta = load_run_meta(root, selected)
st.sidebar.html(pipeline_panel(meta))

description = descriptions.get(selected, "") or "No description in config/scenarios.yaml."
st.html(
    f'<div class="head"><h1>{escape(selected)} <span class="chip">{escape(description)}</span>'
    f'</h1><p class="ledger"><span class="dot"></span><b>Ledger</b>results/{escape(selected)}/'
    f" · solved at commit {escape(str(meta['git_sha']))} · every number on this page is read "
    "from a committed file</p></div>"
)
headline_tiles(root, selected)

tabs = st.tabs(["Overview", "Map", "Capacity and energy", "Teesside hydrogen", "Assumptions"])
with tabs[0]:
    overview(root, selected)
with tabs[1]:
    zone_map(root, selected)
with tabs[2]:
    capacity_and_energy(root, selected)
with tabs[3]:
    hydrogen(root, selected)
with tabs[4]:
    assumptions(root)
