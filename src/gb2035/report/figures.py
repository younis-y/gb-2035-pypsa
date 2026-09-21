"""README figures from results/summary.csv and per-scenario tables.

Colours are the dataviz skill's eight-hue categorical palette (`references/palette.md` in that
skill), validated with `scripts/validate_palette.js` for colourblind-safe adjacent-pair
separation. Hues are assigned in a fixed order per chart and never re-cycled; `teesside_hydrogen`
deliberately pairs slot 1 (blue) with slot 6 (green) instead of two adjacent slots, because the
series are literally "blue hydrogen" and "green hydrogen" - that pair was re-validated directly
(worst-pair Delta E 26.5 CVD / 29.0 normal-vision, both comfortably clear of the >=8 / >=15 gates).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from gb2035.data.fes import fes_value

# Validated categorical palette, fixed order (dataviz skill references/palette.md).
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
MAGENTA = "#e87ba4"
GREEN = "#008300"
VIOLET = "#4a3aa7"
RED = "#e34948"

# Chart chrome, same source.
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "text.color": INK_PRIMARY,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "grid.color": GRIDLINE,
        "grid.linewidth": 0.8,
        "legend.frameon": False,
    }
)

CAP_ORDER = ["uncapped", "cap30", "cap20", "cap10", "cap5", "cap2", "cap0p5"]
TECH_COLS = [
    ("offwind_gw", "Offshore wind", BLUE),
    ("onwind_gw", "Onshore wind", ORANGE),
    ("solar_gw", "Solar", AQUA),
    ("nuclear_gw", "Nuclear", YELLOW),
    ("gas_ccs_gw", "Gas CCS", MAGENTA),
    ("gas_gw", "Unabated gas", GREEN),
    ("battery_gw", "Battery", VIOLET),
    ("h2_turbine_gw_el", "H2 turbine", RED),
]
# Task 11 only splits these carriers' capacity into existing/new (`results/extract.py`
# `summary_row`); controller decision 1 overlays that split where it exists.
NEW_BUILD_COLS: dict[str, str] = {
    "offwind_gw": "offwind_new_gw",
    "onwind_gw": "onwind_new_gw",
    "solar_gw": "solar_new_gw",
    "battery_gw": "battery_new_gw",
}


def _caps(summary: pd.DataFrame) -> pd.DataFrame:
    df = summary[summary["scenario"].isin(CAP_ORDER)].copy()
    df["scenario"] = pd.Categorical(df["scenario"], CAP_ORDER, ordered=True)
    return df.sort_values("scenario")


def capacity_mix_by_cap(summary: pd.DataFrame, out: Path) -> Path:
    df = _caps(summary).set_index("scenario")
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = pd.Series(0.0, index=df.index)
    for col, label, color in TECH_COLS:
        if col in df:
            ax.bar(df.index.astype(str), df[col], bottom=bottom, label=label, color=color)
            bottom = bottom + df[col].fillna(0.0)
    ax.set_ylabel("Installed capacity (GW)")
    ax.set_xlabel("Annual CO2 cap")
    ax.legend(frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = out / "capacity_mix_by_cap.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def cost_and_shadow_price(summary: pd.DataFrame, out: Path) -> Path:
    """Cost and CO2 dual against realised emissions.

    Sorted by emissions, not by cap: `uncapped` is not a cap at all and lands at about 4.6 Mt,
    between `cap5` and `cap2`, so plotting the series in `CAP_ORDER` made the line double back
    on itself.
    """
    df = _caps(summary).sort_values("emissions_mt", ascending=False)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    a1.plot(df["emissions_mt"], df["total_cost_gbp_bn_per_yr"], marker="o", color=BLUE)
    a1.set_xlabel("Emissions (MtCO2/yr)")
    a1.set_ylabel("System cost (bn GBP/yr)")
    a1.invert_xaxis()
    a2.plot(df["emissions_mt"], df["shadow_carbon_price_gbp_per_t"], marker="o", color=ORANGE)
    a2.set_xlabel("Emissions (MtCO2/yr)")
    a2.set_ylabel("Shadow carbon price (GBP/t)")
    a2.invert_xaxis()
    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = out / "cost_and_shadow_price.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _new_build_gw(row: pd.Series, total_col: str) -> float:
    """The greenfield share of `total_col`, or 0 where no `*_new_gw` column exists for it."""
    new_col = NEW_BUILD_COLS.get(total_col)
    if new_col is None or new_col not in row.index or pd.isna(row[new_col]):
        return 0.0
    return float(row[new_col])


def optimised_vs_fes(
    summary: pd.DataFrame, fes: pd.DataFrame, out: Path, scenario: str = "cap2"
) -> Path | None:
    """The model's cap2 (by default) build against FES, or the tightest cap actually solved.

    Mid-sweep, `scenario` may not have a row yet: fall back to the tightest `CAP_ORDER` scenario
    present in `summary` instead of raising, and return `None` (skip the figure) only when no cap
    scenario has been solved at all yet - `make_figures` drops `None`s from its result.
    """
    present = set(summary["scenario"])
    if scenario not in present:
        available = [c for c in CAP_ORDER if c in present]
        if not available:
            return None
        scenario = available[-1]
    row = summary[summary["scenario"] == scenario].iloc[0]
    pairs = [
        ("Offshore wind", "offwind_gw", fes_value(fes, "offshore_wind_gw", "Holistic Transition")),
        ("Onshore wind", "onwind_gw", fes_value(fes, "onshore_wind_gw", "Holistic Transition")),
        ("Solar", "solar_gw", fes_value(fes, "solar_gw", "Holistic Transition")),
        ("Battery", "battery_gw", fes_value(fes, "battery_gw", "Holistic Transition")),
        ("Gas CCS", "gas_ccs_gw", fes_value(fes, "gas_ccus_gw", "Holistic Transition")),
        ("Unabated gas", "gas_gw", fes_value(fes, "unabated_gas_gw", "Holistic Transition")),
    ]
    labels = [label for label, _, _ in pairs]
    new_builds = [_new_build_gw(row, col) for _, col, _ in pairs]
    totals = [float(row[col]) for _, col, _ in pairs]
    existing = [max(total - new, 0.0) for total, new in zip(totals, new_builds, strict=True)]
    fes_values = [value for _, _, value in pairs]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = range(len(labels))
    model_x = [i - 0.2 for i in x]
    fes_x = [i + 0.2 for i in x]
    # Stack the model bar so the greenfield build (hatched) is visible against existing
    # capacity (solid) within the same total-installed bar - controller decision 1. The two
    # segments' labelled values sum to the total installed capacity.
    ax.bar(
        model_x,
        existing,
        width=0.4,
        color=BLUE,
        label=f"This model ({scenario}) - existing capacity",
    )
    ax.bar(
        model_x,
        new_builds,
        width=0.4,
        bottom=existing,
        color=BLUE,
        hatch="///",
        edgecolor=SURFACE,
        linewidth=0,
        label=f"This model ({scenario}) - new build",
    )
    ax.bar(fes_x, fes_values, width=0.4, color=ORANGE, label="FES 2025 Holistic Transition")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("GW in 2035")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = out / "optimised_vs_fes.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def storage_by_cap(summary: pd.DataFrame, out: Path) -> Path:
    df = _caps(summary)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(
        df["scenario"].astype(str), df["battery_gw"], marker="o", color=BLUE, label="Battery (GW)"
    )
    ax.plot(
        df["scenario"].astype(str),
        df["h2_turbine_gw_el"],
        marker="s",
        color=ORANGE,
        label="H2 turbine (GW el)",
    )
    ax.plot(
        df["scenario"].astype(str),
        df["h2_store_gwh"] / 10.0,
        marker="^",
        color=AQUA,
        label="H2 store (GWh / 10)",
    )
    ax.set_xlabel("Annual CO2 cap")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = out / "storage_by_cap.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def teesside_hydrogen(summary: pd.DataFrame, out: Path) -> Path:
    df = _caps(summary).set_index("scenario")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(
        df.index.astype(str),
        df["teesside_green_h2_twh"],
        label="Green (electrolysis)",
        color=GREEN,
    )
    ax.bar(
        df.index.astype(str),
        df["teesside_blue_h2_twh"],
        bottom=df["teesside_green_h2_twh"],
        label="Blue (reforming with CCS)",
        color=BLUE,
    )
    ax.set_ylabel("Teesside hydrogen supply (TWh/yr)")
    ax.set_xlabel("Annual CO2 cap")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = out / "teesside_hydrogen.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def make_figures(
    summary: pd.DataFrame, results_root: Path, fes: pd.DataFrame, out_dir: Path
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[Path | None] = [
        capacity_mix_by_cap(summary, out_dir),
        cost_and_shadow_price(summary, out_dir),
        optimised_vs_fes(summary, fes, out_dir),
        storage_by_cap(summary, out_dir),
        teesside_hydrogen(summary, out_dir),
    ]
    return [path for path in candidates if path is not None]
