"""Every read the app makes, and the caching that keeps a rerun cheap.

The `read_*` functions are pure: a path in, a DataFrame or dict out, no Streamlit involved, so
they are unit-testable on their own. The `load_*` names are the same functions wrapped in
`st.cache_data`, assigned rather than decorated so the pure function stays importable and mypy
strict stays happy whether or not the installed Streamlit ships type information.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

from gb2035.config import load_assumptions
from gb2035.data.zones import LAND_ZONES, ZONE_LABELS
from gb2035.results.summary import ORDER

DEFAULT_SCENARIO = "cap5"
MARKER_FILES: tuple[str, ...] = ("config/scenarios.yaml", "results/summary.csv")
RESULT_TABLES: frozenset[str] = frozenset(
    {
        "capacities",
        "costs",
        "curtailment",
        "duals",
        "emissions",
        "energy",
        "flows",
        "hydrogen",
        "summary_row",
    }
)


def find_project_root(start: Path) -> Path:
    """The nearest directory at or above `start` that holds every file in `MARKER_FILES`."""
    for candidate in (start, *start.parents):
        if all((candidate / rel).exists() for rel in MARKER_FILES):
            return candidate
    msg = f"no gb2035 project root at or above {start}: looked for {', '.join(MARKER_FILES)}"
    raise FileNotFoundError(msg)


def resolve_root(argv: Sequence[str], start: Path) -> Path:
    """`--root <path>` from `streamlit run main.py -- --root <path>`, else discovery.

    Streamlit passes everything after `--` through to the script, and `AppTest` passes nothing,
    so discovery is what runs under test and inside the container.
    """
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 < len(argv):
            return Path(argv[index + 1]).resolve()
    return find_project_root(start)


@dataclass(frozen=True)
class Headline:
    """One metric on the Overview view: which summary column, and how it reads."""

    column: str
    label: str
    fmt: str
    note: str


HEADLINES: tuple[Headline, ...] = (
    Headline(
        "total_cost_gbp_bn_per_yr",
        "System cost",
        "{:.2f} bn GBP/yr",
        "Annualised capital, fixed and variable operating cost, from results/summary.csv.",
    ),
    Headline(
        "emissions_mt",
        "Emissions",
        "{:.1f} MtCO2/yr",
        "Territorial power-sector CO2. Imports carry no emissions in this model.",
    ),
    Headline(
        "shadow_carbon_price_gbp_per_t",
        "Shadow carbon price",
        "{:.0f} GBP/t",
        "Dual of the CO2 cap. Zero where the cap is slack or absent.",
    ),
    Headline(
        "net_imports_twh",
        "Net imports",
        "{:+.1f} TWh",
        "Interconnector imports minus exports over the year.",
    ),
    Headline(
        "curtailed_share_wind_solar",
        "Wind and solar curtailed",
        "{:.1%}",
        "Share of available wind and solar energy the optimiser did not use.",
    ),
)


def headline_values(row: pd.Series) -> list[tuple[str, str, str]]:
    """(label, formatted value, note) for each headline metric of one summary row."""
    return [(h.label, h.fmt.format(float(row[h.column])), h.note) for h in HEADLINES]


def read_summary(root: Path) -> pd.DataFrame:
    return pd.read_csv(root / "results" / "summary.csv")


def _require_known_scenario(root: Path, scenario: str) -> None:
    """Reject a `scenario` that `available_scenarios` did not itself discover under `results/`.

    `scenario` (and `table`, in `read_scenario_table` below) can come from outside the process
    — a Streamlit `st.query_params` value, say — so it must never be trusted as a bare path
    segment: a string such as "../../../etc" or "/etc" joins straight through
    `Path.__truediv__` and can walk the read right out of `results/`. Restricting `scenario` to
    a name this function already found on disk closes that off entirely: everything downstream
    only ever joins a literal, known-good directory name.
    """
    known = available_scenarios(root)
    if scenario not in known:
        msg = f"unknown scenario {scenario!r}; known: {known}"
        raise ValueError(msg)


def read_scenario_table(root: Path, scenario: str, table: str) -> pd.DataFrame:
    _require_known_scenario(root, scenario)
    if table not in RESULT_TABLES:
        msg = f"unknown result table {table!r}; known: {sorted(RESULT_TABLES)}"
        raise ValueError(msg)
    path = root / "results" / scenario / f"{table}.csv"
    if not path.exists():
        msg = f"{path} is not a committed result table"
        raise FileNotFoundError(msg)
    return pd.read_csv(path)


def read_run_meta(root: Path, scenario: str) -> dict[str, Any]:
    _require_known_scenario(root, scenario)
    path = root / "results" / scenario / "run_meta.json"
    if not path.exists():
        msg = f"{path} is not a committed run_meta.json"
        raise FileNotFoundError(msg)
    meta: dict[str, Any] = json.loads(path.read_text())
    return meta


def available_scenarios(root: Path) -> list[str]:
    """Scenario directories that carry a summary row, in the report's own order."""
    names = [p.parent.name for p in (root / "results").glob("*/summary_row.csv")]
    rank = {name: i for i, name in enumerate(ORDER)}
    return sorted(names, key=lambda name: (rank.get(name, len(ORDER)), name))


def scenario_descriptions(root: Path) -> dict[str, str]:
    doc = yaml.safe_load((root / "config" / "scenarios.yaml").read_text()) or {}
    scenarios: dict[str, Any] = doc.get("scenarios", {})
    return {name: str((body or {}).get("description", "")) for name, body in scenarios.items()}


def read_assumptions_table(root: Path) -> pd.DataFrame:
    """`config/assumptions.yaml` as a table, validated through the project's own model."""
    assumptions = load_assumptions(root / "config" / "assumptions.yaml")
    return pd.DataFrame(
        [
            {
                "key": key,
                "value": a.value,
                "unit": a.unit,
                "confidence": a.confidence,
                "source": a.source,
                "note": a.note,
            }
            for key, a in sorted(assumptions.items())
        ],
        columns=["key", "value", "unit", "confidence", "source", "note"],
    )


@dataclass(frozen=True)
class MapMetric:
    """One choropleth colour source: which `zone_metrics` column, and its unit."""

    column: str
    unit: str


MAP_METRICS: dict[str, MapMetric] = {
    "New-build capacity (GW)": MapMetric("new_build_gw", "GW"),
    "Total generation capacity (GW)": MapMetric("total_capacity_gw", "GW"),
    "Demand-weighted price (GBP/MWh)": MapMetric("price_gbp_per_mwh", "GBP/MWh"),
}
# `capacities.csv` lists `ic * import` and `ic * export` at full capacity each, so summing both
# legs would double-count the 19.4 GW of physical interconnection (README, "What this model
# does not claim"). Zone capacity counts generation and storage only.
TRADE_CARRIERS: frozenset[str] = frozenset({"import", "export"})
PRICE_METRIC = "demand_weighted_price_gbp_per_mwh"


def read_zone_geojson(root: Path) -> dict[str, Any]:
    """The committed zone polygons: 20 land zones plus the three offshore lease areas."""
    geojson: dict[str, Any] = json.loads((root / "data" / "derived" / "zones.geojson").read_text())
    return geojson


def read_bus_coordinates(root: Path) -> pd.DataFrame:
    return pd.read_csv(root / "data" / "derived" / "buses.csv")


def _as_bool(series: pd.Series) -> pd.Series:
    """`existing` is bool in the committed CSVs; coerce a string column without lying."""
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().str.lower().eq("true")


def zone_metrics(capacities: pd.DataFrame, duals: pd.DataFrame) -> pd.DataFrame:
    """One row per land zone: new build, total capacity and the demand-weighted price."""
    built = capacities[
        capacities["component"].isin(["Generator", "StorageUnit"])
        & capacities["zone"].isin(LAND_ZONES)
        & ~capacities["carrier"].isin(TRADE_CARRIERS)
    ]
    existing = _as_bool(built["existing"])
    total = built.groupby("zone")["p_nom_opt"].sum() / 1e3
    new = built[~existing].groupby("zone")["p_nom_opt"].sum() / 1e3
    price = duals[duals["metric"] == PRICE_METRIC].set_index("zone")["value"]
    index = pd.Index(list(LAND_ZONES), name="zone")
    out = pd.DataFrame(index=index)
    out["zone_name"] = [ZONE_LABELS[zone] for zone in index]
    out["new_build_gw"] = new.reindex(index).fillna(0.0)
    out["total_capacity_gw"] = total.reindex(index).fillna(0.0)
    out["price_gbp_per_mwh"] = price.reindex(index)
    return out.reset_index()


def corridor_flows(flows: pd.DataFrame, buses: pd.DataFrame) -> pd.DataFrame:
    """`flows.csv` with each corridor's endpoints and midpoint taken from the bus coordinates."""
    coords = buses.set_index("name")
    out = flows.copy()
    out["net_twh"] = out["twh_forward"] - out["twh_reverse"]
    out["lon0"] = out["bus0"].map(coords["x"])
    out["lat0"] = out["bus0"].map(coords["y"])
    out["lon1"] = out["bus1"].map(coords["x"])
    out["lat1"] = out["bus1"].map(coords["y"])
    out["lon_mid"] = (out["lon0"] + out["lon1"]) / 2.0
    out["lat_mid"] = (out["lat0"] + out["lat1"]) / 2.0
    out["label"] = out["bus0"] + " to " + out["bus1"]
    return out.dropna(subset=["lon0", "lat0", "lon1", "lat1"]).reset_index(drop=True)


# Cached views of the readers above. Assigned, not decorated: the pure function stays
# importable for the unit tests, and mypy strict accepts the assignment whether or not the
# installed Streamlit ships type information.
load_summary = st.cache_data(show_spinner=False)(read_summary)
load_scenario_table = st.cache_data(show_spinner=False)(read_scenario_table)
load_run_meta = st.cache_data(show_spinner=False)(read_run_meta)
load_assumptions_table = st.cache_data(show_spinner=False)(read_assumptions_table)
load_zone_geojson = st.cache_data(show_spinner=False)(read_zone_geojson)
load_bus_coordinates = st.cache_data(show_spinner=False)(read_bus_coordinates)
