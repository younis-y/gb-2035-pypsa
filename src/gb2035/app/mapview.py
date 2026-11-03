"""The zone map: a choropleth over the 20 land zones, corridor flows on top.

`go.Choroplethmap` and `go.Scattermap` are the MapLibre traces, so nothing here needs a Mapbox
token. The default style is a single graphite background layer with no tile source: the zone
polygons carry the geography, so the app and the static README export both render with no tile
server at all.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from gb2035.app.palette import (
    BLUE_INK,
    FONT_FAMILY,
    INK,
    MUTED,
    ORANGE,
    PANEL,
    RAISED,
    RED,
    RIM,
)
from gb2035.data.zones import OFFSHORE_ZONES, ZONE_LABELS

# The Teesside industrial cluster, the site the `Teesside H2` bus stands for. A location, not a
# model result; the same coordinate the zone assignment test uses for Teesside.
TEESSIDE_LATLON: tuple[float, float] = (54.60, -1.15)
GB_CENTRE: dict[str, float] = {"lat": 55.3, "lon": -3.2}
GB_ZOOM = 4.2
MAP_HEIGHT = 760
COLOURSCALE: list[list[Any]] = [[0.0, "#3A404B"], [0.5, "#3767C4"], [1.0, BLUE_INK]]
# A MapLibre style with one background layer and no sources: nothing to fetch, ever.
GRAPHITE_STYLE: dict[str, Any] = {
    "version": 8,
    "sources": {},
    "layers": [{"id": "background", "type": "background", "paint": {"background-color": PANEL}}],
}
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
    map_style: str | dict[str, Any] = GRAPHITE_STYLE,
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
            marker={"opacity": 0.92, "line": {"width": 1, "color": PANEL}},
            # Under the map, not beside it: a vertical bar would sit on the offshore areas.
            colorbar={
                "title": {"text": metric_label, "side": "top", "font": {"color": INK}},
                "orientation": "h",
                "x": 0.5,
                "y": 0.02,
                "xanchor": "center",
                "yanchor": "bottom",
                "len": 0.7,
                "thickness": 10,
                "tickfont": {"color": MUTED},
                "outlinewidth": 0,
            },
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
            colorscale=[[0.0, PANEL], [1.0, PANEL]],
            showscale=False,
            marker={"opacity": 0.9, "line": {"width": 1, "color": RIM}},
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
        paper_bgcolor=PANEL,
        font={"family": FONT_FAMILY, "color": INK, "size": 13},
        hoverlabel={"bgcolor": RAISED, "bordercolor": RIM, "font": {"color": INK}},
    )
    return fig
