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
from gb2035.results.summary import ORDER

DEFAULT_SCENARIO = "cap5"
MARKER_FILES: tuple[str, ...] = ("config/scenarios.yaml", "results/summary.csv")


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


def read_scenario_table(root: Path, scenario: str, table: str) -> pd.DataFrame:
    path = root / "results" / scenario / f"{table}.csv"
    if not path.exists():
        msg = f"{path} is not a committed result table"
        raise FileNotFoundError(msg)
    return pd.read_csv(path)


def read_run_meta(root: Path, scenario: str) -> dict[str, Any]:
    path = root / "results" / scenario / "run_meta.json"
    meta: dict[str, Any] = json.loads(path.read_text())
    return meta


def available_scenarios(root: Path) -> list[str]:
    """Scenario directories that carry a summary row, in the report's own order."""
    names = sorted(p.parent.name for p in (root / "results").glob("*/summary_row.csv"))
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


# Cached views of the readers above. Assigned, not decorated: the pure function stays
# importable for the unit tests, and mypy strict accepts the assignment whether or not the
# installed Streamlit ships type information.
load_summary = st.cache_data(show_spinner=False)(read_summary)
load_scenario_table = st.cache_data(show_spinner=False)(read_scenario_table)
load_run_meta = st.cache_data(show_spinner=False)(read_run_meta)
load_assumptions_table = st.cache_data(show_spinner=False)(read_assumptions_table)
