# The results explorer

A read-only Streamlit app over the committed artefacts. It does not build or solve a network,
it writes nothing, and it holds no numbers of its own: every figure and metric is read at
runtime from a file in this repository, so the app cannot disagree with `results/`.

```bash
uv run gb2035 app                 # or: uv run streamlit run src/gb2035/app/main.py -- --root .
docker run -p 8501:8501 ghcr.io/younis-y/gb-2035-pypsa:latest
```

The scenario selector in the sidebar lists every directory under `results/` that carries a
`summary_row.csv`, in the order `results/summary.csv` uses. The description beside it comes from
`config/scenarios.yaml`.

## Overview

Five headline metrics for the selected scenario, read from `results/summary.csv`: system cost
(bn GBP/yr), emissions (MtCO2/yr), the shadow carbon price (GBP/t, the dual of the CO2 cap),
net interconnector imports (TWh) and the share of available wind and solar that was curtailed.

Below them, system cost and the shadow carbon price against realised emissions across the cap
sweep, with the selected scenario ringed. The series is ordered by emissions rather than by cap
name, because `uncapped` is not a cap and lands mid-sweep; ordering by name makes the line
double back on itself. The footer line comes from `results/<scenario>/run_meta.json`: PyPSA
version, commit, snapshot count, resolution, solver and solve time.

## Map

The land zones from `data/derived/zones.geojson`, shaded by one of three metrics:

| Metric | Built from |
|---|---|
| New-build capacity (GW) | `results/<scenario>/capacities.csv`, generation and storage the optimiser added (`existing` is false) |
| Total generation capacity (GW) | the same file, every generation and storage row |
| Demand-weighted price (GBP/MWh) | `results/<scenario>/duals.csv`, `demand_weighted_price_gbp_per_mwh` |

Interconnector import and export legs are excluded from both capacity metrics: `capacities.csv`
lists each leg at the full interconnector capacity, so summing them would double-count the
physical interconnection.

The inter-zone corridors are drawn as lines between the zone bus coordinates in
`data/derived/buses.csv`, their width scaled by net annual energy from
`results/<scenario>/flows.csv`. Hovering the midpoint marker gives the corridor's capacity, net
flow, peak utilisation and the share of hours it sat at capacity. The three offshore lease areas
are outlined in grey and carry no metric, because their generators are modelled at their landing
buses (Z8 and Z12). The red marker is the `Teesside H2` bus, coupled to Z7.

Curtailment is not on this map. `results/<scenario>/curtailment.csv` is a whole-system split by
carrier, and a per-zone version would need `network.nc`, which is git-ignored, so it is not
available to a fresh clone or to the container. The Capacity and energy view shows the
system-wide figure instead.

## Capacity and energy

Installed capacity by technology across the cap sweep, stacked, from `results/summary.csv`;
then annual electricity by carrier for the selected scenario from
`results/<scenario>/energy.csv`, electricity rows only. Exports and electrolysis are withdrawals
and plot negative. The hydrogen rows (`bus_carrier == "H2"`) are measured in hydrogen and are
never added to the power rows. Below the charts, `results/<scenario>/curtailment.csv`: available
energy, used energy and the curtailed share for onshore wind, offshore wind and solar.

## Teesside hydrogen

`results/<scenario>/hydrogen.csv` in full: electrolysis capacity and utilisation, green
hydrogen, store size, hydrogen turbine capacity, hydrogen to power, blue hydrogen and the
industrial demand. Underneath it, `docs/figures/teesside_hydrogen.png`, the cross-scenario green
against blue split that `gb2035 report` writes.

## Assumptions

`config/assumptions.yaml` as a filterable table: key, value, unit, confidence and source. Every
row carries a source URL and one of three confidence tags (published, derived, assumption).
Technology capex, fixed and variable O&M, efficiencies and lifetimes are not here: they are in
`data/derived/costs_2035_gb.csv`, one source per row.

## Two deviations from the design spec

- **Plotly, not folium.** Spec section 12 named a folium choropleth. The app uses Plotly's
  MapLibre traces (`Choroplethmap`, `Scattermap`) so that one charting library covers the charts
  and the map and the map needs no Mapbox token.
- **No Dispatch view.** Spec section 12 listed a Dispatch page with a week picker. Its input,
  `results/<scenario>/dispatch_hourly.parquet`, is deliberately git-ignored, so a fresh clone
  and the published image have no data for it. Regenerate it with
  `uv run gb2035 run --scenario <name>` if you want the hourly series locally.
