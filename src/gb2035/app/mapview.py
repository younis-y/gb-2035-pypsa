"""The zone map: a choropleth over the 20 land zones, corridor flows on top.

`go.Choroplethmap` and `go.Scattermap` are the MapLibre traces, so nothing here needs a Mapbox
token. `map_style="open-street-map"` fetches tiles in the browser; the static README export
passes `map_style="white-bg"` so it renders with no tile server at all.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from gb2035.app.palette import (
    BASELINE,
    BLUE,
    FONT_FAMILY,
    GRIDLINE,
    INK_PRIMARY,
    ORANGE,
    RED,
    SURFACE,
)
from gb2035.data.zones import OFFSHORE_ZONES, ZONE_LABELS

# The Teesside industrial cluster, the site the `Teesside H2` bus stands for. A location, not a
# model result; the same coordinate the zone assignment test uses for Teesside.
TEESSIDE_LATLON: tuple[float, float] = (54.60, -1.15)
GB_CENTRE: dict[str, float] = {"lat": 55.3, "lon": -3.2}
GB_ZOOM = 4.2
MAP_HEIGHT = 760
COLOURSCALE: list[list[Any]] = [[0.0, "#eef4fc"], [0.5, "#8ab4e8"], [1.0, BLUE]]
ZONE_HOVER = (
    "<b>%{customdata[0]}</b> (%{location})<br>"
    "New build %{customdata[1]:.2f} GW<br>"
    "Total capacity %{customdata[2]:.2f} GW<br>"
    "Demand-weighted price %{customdata[3]:.2f} GBP/MWh"
    "<extra></extra>"
)


def line_widths(net_twh: pd.Series) -> pd.Series:
    """Corridor line width, 1 to 6 points, scaled by net annual energy."""
    scale = float(net_twh.abs().max()) if len(net_twh) else 0.0
    if scale <= 0:
        return pd.Series(1.5, index=net_twh.index, dtype=float)
    return 1.0 + 5.0 * net_twh.abs() / scale


def zone_choropleth(
    geojson: dict[str, Any],
    metrics: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    metric: str,
    metric_label: str,
    hover_unit: str,
    map_style: str = "open-street-map",
) -> go.Figure:
    """Land zones coloured by `metric`, corridors as lines, the Teesside node marked."""
    customdata = metrics[
        ["zone_name", "new_build_gw", "total_capacity_gw", "price_gbp_per_mwh"]
    ].to_numpy()
    fig = go.Figure(
        go.Choroplethmap(
            geojson=geojson,
            featureidkey="properties.Name_1",
            locations=metrics["zone"],
            z=metrics[metric],
            customdata=customdata,
            hovertemplate=ZONE_HOVER,
            colorscale=COLOURSCALE,
            marker={"opacity": 0.82, "line": {"width": 1, "color": SURFACE}},
            colorbar={"title": {"text": f"{metric_label}<br>({hover_unit})"}, "thickness": 14},
            name="",
        )
    )
    # The offshore lease areas carry no zone metric: their generators are modelled at the
    # landing buses (Z8, Z12), so they are context, not data.
    fig.add_trace(
        go.Choroplethmap(
            geojson=geojson,
            featureidkey="properties.Name_1",
            locations=list(OFFSHORE_ZONES),
            z=[0.0] * len(OFFSHORE_ZONES),
            colorscale=[[0.0, GRIDLINE], [1.0, GRIDLINE]],
            showscale=False,
            marker={"opacity": 0.35, "line": {"width": 1, "color": BASELINE}},
            text=[ZONE_LABELS[zone] for zone in OFFSHORE_ZONES],
            hovertemplate="<b>%{text}</b><br>offshore lease area<extra></extra>",
            name="",
        )
    )
    widths = line_widths(flows["net_twh"])
    for position, (_, corridor) in enumerate(flows.iterrows()):
        fig.add_trace(
            go.Scattermap(
                lat=[corridor["lat0"], corridor["lat1"]],
                lon=[corridor["lon0"], corridor["lon1"]],
                mode="lines",
                line={"width": float(widths.iloc[position]), "color": ORANGE},
                hoverinfo="skip",
                showlegend=False,
                name="",
            )
        )
    fig.add_trace(
        go.Scattermap(
            lat=flows["lat_mid"],
            lon=flows["lon_mid"],
            mode="markers",
            marker={"size": 7, "color": ORANGE},
            customdata=flows[
                ["label", "p_nom_total_mw", "net_twh", "max_utilisation", "hours_congested_share"]
            ].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Capacity %{customdata[1]:,.0f} MW<br>"
                "Net flow %{customdata[2]:.2f} TWh<br>"
                "Peak utilisation %{customdata[3]:.0%}<br>"
                "Hours at capacity %{customdata[4]:.1%}"
                "<extra></extra>"
            ),
            showlegend=False,
            name="",
        )
    )
    fig.add_trace(
        go.Scattermap(
            lat=[TEESSIDE_LATLON[0]],
            lon=[TEESSIDE_LATLON[1]],
            mode="markers",
            marker={"size": 13, "color": RED},
            hovertemplate="<b>Teesside H2 node</b><br>hydrogen bus, coupled to Z7<extra></extra>",
            showlegend=False,
            name="",
        )
    )
    fig.update_layout(
        map={"style": map_style, "center": GB_CENTRE, "zoom": GB_ZOOM},
        height=MAP_HEIGHT,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor=SURFACE,
        font={"family": FONT_FAMILY, "color": INK_PRIMARY, "size": 13},
    )
    return fig
