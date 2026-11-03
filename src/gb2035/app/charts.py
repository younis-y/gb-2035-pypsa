"""Plotly figures for the app: a DataFrame in, a `go.Figure` out, no Streamlit involved."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gb2035.app.palette import (
    AQUA,
    BLUE_INK,
    CAP_ORDER,
    CARRIER_COLOURS,
    FONT_FAMILY,
    INK,
    INK_MUTED,
    MUTED,
    ORANGE,
    PANEL,
    RAISED,
    RIM,
    RULE,
    TECH_SERIES,
)

CHART_HEIGHT = 420


def _style(fig: go.Figure, height: int = CHART_HEIGHT) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font={"family": FONT_FAMILY, "color": INK, "size": 13},
        margin={"l": 64, "r": 24, "t": 56, "b": 44},
        legend={"orientation": "h", "yanchor": "top", "y": -0.16, "x": 0, "font": {"color": MUTED}},
        hoverlabel={"bgcolor": RAISED, "bordercolor": RIM, "font": {"color": INK}},
        hovermode="closest",
    )
    axes = {"gridcolor": RULE, "linecolor": RIM, "zeroline": False, "tickfont": {"color": MUTED}}
    fig.update_xaxes(**axes)
    fig.update_yaxes(**axes)
    return fig


def cap_scenarios(summary: pd.DataFrame) -> pd.DataFrame:
    """The cap sweep only, ordered by realised emissions.

    `uncapped` is not a cap at all and lands mid-sweep on emissions, so ordering by cap name
    makes the line double back on itself (`report/figures.py` makes the same choice).
    """
    df = summary[summary["scenario"].isin(CAP_ORDER)].copy()
    return df.sort_values("emissions_mt", ascending=False).reset_index(drop=True)


def cost_and_shadow_price_figure(summary: pd.DataFrame, highlight: str) -> go.Figure:
    """System cost and the CO2 dual against realised emissions, with one scenario picked out."""
    df = cap_scenarios(summary)
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("System cost", "Shadow carbon price"),
        horizontal_spacing=0.12,
    )
    panels = (
        (1, "total_cost_gbp_bn_per_yr", "bn GBP/yr", BLUE_INK),
        (2, "shadow_carbon_price_gbp_per_t", "GBP/t", ORANGE),
    )
    for col, column, unit, colour in panels:
        fig.add_trace(
            go.Scatter(
                x=df["emissions_mt"],
                y=df[column],
                mode="lines+markers",
                name=unit,
                showlegend=False,
                line={"color": colour, "width": 2},
                marker={"size": 8, "color": colour},
                customdata=df[["scenario"]].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{x:.1f} MtCO2/yr<br>"
                    f"%{{y:.2f}} {unit}<extra></extra>"
                ),
            ),
            row=1,
            col=col,
        )
    chosen = df[df["scenario"] == highlight]
    for col, column, _unit, colour in panels:
        if chosen.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=chosen["emissions_mt"],
                y=chosen[column],
                mode="markers",
                showlegend=False,
                hoverinfo="skip",
                marker={"size": 16, "color": colour, "line": {"width": 2, "color": INK}},
            ),
            row=1,
            col=col,
        )
    fig.update_xaxes(title_text="Emissions (MtCO2/yr)", autorange="reversed")
    fig.update_yaxes(title_text="bn GBP/yr", row=1, col=1)
    fig.update_yaxes(title_text="GBP/t", row=1, col=2)
    return _style(fig)


def capacity_mix_figure(summary: pd.DataFrame) -> go.Figure:
    """Installed capacity by technology across the cap sweep."""
    df = cap_scenarios(summary)
    fig = go.Figure()
    for column, label, colour in TECH_SERIES:
        fig.add_trace(
            go.Bar(
                x=df["scenario"],
                y=df[column],
                name=label,
                marker_color=colour,
                hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.1f}} GW<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="Installed capacity (GW)")
    return _style(fig, height=460)


def energy_mix_figure(energy: pd.DataFrame, scenario: str) -> go.Figure:
    """Annual electricity by carrier for one scenario.

    Only `bus_carrier == "AC"` rows are plotted: the hydrogen rows are measured in hydrogen and
    must never be added to the power rows (`results/extract.py`). Exports and electrolysis are
    negative, which is the point of the chart.
    """
    ac = energy[energy["bus_carrier"] == "AC"].sort_values("twh", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=ac["carrier"],
            y=ac["twh"],
            marker_color=[CARRIER_COLOURS.get(c, INK_MUTED) for c in ac["carrier"]],
            hovertemplate="%{x}<br>%{y:.1f} TWh<extra></extra>",
        )
    )
    fig.update_yaxes(title_text="TWh per year")
    fig.update_xaxes(title_text=f"Carrier ({scenario}, electricity only)")
    return _style(fig)


def hydrogen_supply_figure(summary: pd.DataFrame) -> go.Figure:
    """Teesside hydrogen supply across the cap sweep, green stacked under blue.

    The app's own render of `docs/figures/teesside_hydrogen.png`, so it sits on the graphite
    theme instead of a white matplotlib panel.
    """
    df = cap_scenarios(summary)
    fig = go.Figure()
    for column, label, colour in (
        ("teesside_green_h2_twh", "Green (electrolysis)", AQUA),
        ("teesside_blue_h2_twh", "Blue (reforming with CCS)", BLUE_INK),
    ):
        fig.add_trace(
            go.Bar(
                x=df["scenario"],
                y=df[column],
                name=label,
                marker_color=colour,
                hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.2f}} TWh<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="Teesside hydrogen supply (TWh/yr)")
    return _style(fig)
