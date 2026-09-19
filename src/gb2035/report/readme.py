"""Render the cross-scenario summary into the README between markers."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

START, END = "<!-- summary:start -->", "<!-- summary:end -->"
COLUMNS = [
    ("scenario", "Scenario", "{}"),
    ("emissions_mt", "CO2 (Mt)", "{:.1f}"),
    ("total_cost_gbp_bn_per_yr", "System cost (bn GBP/yr)", "{:.1f}"),
    ("shadow_carbon_price_gbp_per_t", "Shadow carbon price (GBP/t)", "{:.0f}"),
    ("onwind_gw", "Onshore (GW)", "{:.0f}"),
    ("offwind_gw", "Offshore (GW)", "{:.0f}"),
    ("solar_gw", "Solar (GW)", "{:.0f}"),
    ("battery_gw", "Battery (GW)", "{:.0f}"),
    ("electrolysis_gw", "Electrolysis (GW)", "{:.1f}"),
    ("teesside_green_h2_twh", "Green H2 (TWh)", "{:.1f}"),
    ("teesside_blue_h2_twh", "Blue H2 (TWh)", "{:.1f}"),
]


def summary_markdown(summary: pd.DataFrame) -> str:
    cols = [c for c in COLUMNS if c[0] in summary.columns]
    header = "| " + " | ".join(h for _, h, _ in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    lines = [header, sep]
    for _, row in summary.iterrows():
        lines.append("| " + " | ".join(fmt.format(row[c]) for c, _, fmt in cols) + " |")
    return "\n".join(lines)


def update_readme(readme: Path, block: str) -> None:
    text = readme.read_text()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        msg = f"{readme} lacks the summary markers"
        raise ValueError(msg)
    readme.write_text(pattern.sub(f"{START}\n{block}\n{END}", text))
