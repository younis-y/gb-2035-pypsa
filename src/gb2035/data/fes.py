"""Read headline 2035 figures out of the NESO FES 2025 data workbook.

Each chart sheet holds one or more blocks: a header row whose cells are datetimes (one per
year) preceded by a unit cell, followed by one row per pathway with the label in the same
column as the unit. Blocks are numbered from zero in sheet order.
"""

from __future__ import annotations

import datetime as dt
import warnings
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd

FES_METRICS: dict[str, tuple[str, int, str]] = {
    "consumer_demand_twh": ("F.53", 0, "TWh"),
    "peak_demand_gw": ("F.54", 0, "GW"),
    "offshore_wind_gw": ("F.55", 0, "GW"),
    "onshore_wind_gw": ("F.56", 0, "GW"),
    "solar_gw": ("F.57", 0, "GW"),
    "battery_gw": ("F.59", 0, "GW"),
    "ldes_gw": ("F.60", 0, "GW"),
    "interconnector_gw": ("F.61", 0, "GW"),
    "nuclear_gw": ("F.62", 0, "GW"),
    "hydrogen_generation_gw": ("F.63", 0, "GW"),
    "gas_ccus_gw": ("F.63", 1, "GW"),
    "unabated_gas_gw": ("F.64", 0, "GW"),
    "industrial_h2_twh": ("F.51", 0, "TWh"),
}
PATHWAYS: tuple[str, ...] = (
    "Holistic Transition",
    "Electric Engagement",
    "Hydrogen Evolution",
    "Falling Behind",
    "Ten Year Forecast",
)


def _blocks(rows: list[tuple[Any, ...]], year: int) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for i, row in enumerate(rows):
        year_cols = {c.year: j for j, c in enumerate(row) if isinstance(c, dt.datetime)}
        if len(year_cols) < 5 or year not in year_cols:
            continue
        col = year_cols[year]
        block: dict[str, float] = {}
        for later in rows[i + 1 : i + 12]:
            label = next((c for c in later if isinstance(c, str)), None)
            if label is None:
                break
            value = later[col] if col < len(later) else None
            if label.strip() in PATHWAYS and isinstance(value, int | float):
                block[label.strip()] = float(value)
        out.append(block)
    return out


def extract_fes_2035(workbook: Path, year: int = 2035) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    records: list[dict[str, Any]] = []
    for metric, (sheet, block_index, unit) in FES_METRICS.items():
        rows = list(wb[sheet].iter_rows(values_only=True))
        blocks = _blocks(rows, year)
        if block_index >= len(blocks):
            msg = f"{sheet}: wanted block {block_index}, found {len(blocks)}"
            raise ValueError(msg)
        for pathway, value in blocks[block_index].items():
            records.append(
                {
                    "metric": metric,
                    "pathway": pathway,
                    "value": value,
                    "unit": unit,
                    "sheet": sheet,
                    "block": block_index,
                }
            )
    wb.close()
    return pd.DataFrame.from_records(
        records, columns=["metric", "pathway", "value", "unit", "sheet", "block"]
    )


def load_fes(csv: Path) -> pd.DataFrame:
    return pd.read_csv(csv)


def fes_value(fes: pd.DataFrame, metric: str, pathway: str) -> float:
    rows = fes[(fes["metric"] == metric) & (fes["pathway"] == pathway)]
    if rows.empty:
        msg = f"no FES value for {metric!r} / {pathway!r}"
        raise KeyError(msg)
    return float(rows["value"].iloc[0])
