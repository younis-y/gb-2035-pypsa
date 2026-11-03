"""The dataviz palette shared by the matplotlib report and the Plotly app.

Validated categorical colours and chart chrome (`references/palette.md` in the dataviz skill,
checked with `scripts/validate_palette.js` for colourblind-safe adjacent-pair separation). Both
`gb2035.report.figures` (matplotlib) and `gb2035.app.palette` (Plotly) import their constants
from here, so the two renderers can never drift apart. This module must never import matplotlib
or streamlit: it is imported by the read-only app, which has no business pulling in either
rendering stack.
"""

from __future__ import annotations

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
