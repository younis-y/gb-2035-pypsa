"""The dataviz palette the README figures use, restated for Plotly.

The colour and chrome constants come from `gb2035.palette`, the module shared with
`gb2035.report.figures` (matplotlib). That module switches the matplotlib backend at import
time, which the app has no business doing, so this module imports the constants directly from
the shared source instead - it never imports `gb2035.report.figures`. The re-export below is
pinned to `gb2035.report.figures` by
`tests/unit/test_app_charts.py::test_palette_matches_the_readme_figures`, so the two renderers
cannot drift apart.
"""

from __future__ import annotations

from gb2035.palette import (
    AQUA,
    BASELINE,
    BLUE,
    GREEN,
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    MAGENTA,
    ORANGE,
    RED,
    SURFACE,
    VIOLET,
    YELLOW,
)

__all__ = [
    "AQUA",
    "BASELINE",
    "BLUE",
    "CAP_ORDER",
    "CARRIER_COLOURS",
    "FONT_FAMILY",
    "GREEN",
    "GRIDLINE",
    "INK_MUTED",
    "INK_PRIMARY",
    "INK_SECONDARY",
    "MAGENTA",
    "ORANGE",
    "RED",
    "SURFACE",
    "TECH_SERIES",
    "VIOLET",
    "YELLOW",
]

FONT_FAMILY = "system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"

CAP_ORDER: tuple[str, ...] = ("uncapped", "cap30", "cap20", "cap10", "cap5", "cap2", "cap0p5")

# (summary.csv column, label, colour), in the README figure's order.
TECH_SERIES: tuple[tuple[str, str, str], ...] = (
    ("offwind_gw", "Offshore wind", BLUE),
    ("onwind_gw", "Onshore wind", ORANGE),
    ("solar_gw", "Solar", AQUA),
    ("nuclear_gw", "Nuclear", YELLOW),
    ("gas_ccs_gw", "Gas CCS", MAGENTA),
    ("gas_gw", "Unabated gas", GREEN),
    ("battery_gw", "Battery", VIOLET),
    ("h2_turbine_gw_el", "H2 turbine", RED),
)

# Every carrier that appears in a committed `energy.csv`, plus the hydrogen rows the energy
# chart filters out, so the lookup never falls through.
CARRIER_COLOURS: dict[str, str] = {
    "offwind": BLUE,
    "onwind": ORANGE,
    "solar": AQUA,
    "nuclear": YELLOW,
    "gas_ccs": MAGENTA,
    "gas": GREEN,
    "battery": VIOLET,
    "h2_turbine": RED,
    "pumped_hydro": INK_SECONDARY,
    "import": AQUA,
    "export": BASELINE,
    "electrolysis": VIOLET,
    "blue_h2": BLUE,
    "h2_store": INK_MUTED,
}
