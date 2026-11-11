"""Assemble a pypsa.Network for one scenario."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any, cast

import pandas as pd
import pypsa

from gb2035.config import Scenario, Settings
from gb2035.data.demand import HOURS_PER_YEAR
from gb2035.model.components import (
    add_buses,
    add_carriers,
    add_hydrogen_cluster,
    add_interconnectors,
    add_links,
    add_loads,
    add_renewables,
    add_storage,
    add_thermal,
)
from gb2035.model.constraints import add_co2_cap, add_fes_capacity_ceiling, add_steel_loads
from gb2035.model.inputs import ModelInputs


def select_snapshots(
    demand_index: pd.DatetimeIndex, scenario: Scenario, settings: Settings
) -> pd.DatetimeIndex:
    idx = demand_index
    if scenario.snapshots is not None:
        end = pd.Timestamp(scenario.snapshots.end) + pd.Timedelta(hours=23)
        idx = idx[(idx >= pd.Timestamp(scenario.snapshots.start)) & (idx <= end)]
    if settings.resolution_hours > 1:
        idx = idx[:: settings.resolution_hours]
    if len(idx) == 0:
        msg = "snapshot selection is empty"
        raise ValueError(msg)
    return pd.DatetimeIndex(idx)


def build_network(inputs: ModelInputs, scenario: Scenario, settings: Settings) -> pypsa.Network:
    if scenario.capex_scale:
        costs = inputs.costs.copy()
        for tech, factor in scenario.capex_scale.items():
            costs.loc[tech, "capex_gbp"] = float(cast(Any, costs.at[tech, "capex_gbp"])) * factor
        inputs = replace(inputs, costs=costs)
    n = pypsa.Network(name=f"gb2035 {scenario.name}")
    snapshots = select_snapshots(pd.DatetimeIndex(inputs.demand.index), scenario, settings)
    n.set_snapshots(cast(Any, snapshots))
    weight = HOURS_PER_YEAR / len(snapshots)
    n.snapshot_weightings.loc[:, ["objective", "generators"]] = weight
    n.snapshot_weightings.loc[:, "stores"] = float(settings.resolution_hours)
    add_carriers(n, scenario, settings)
    add_buses(n, inputs)
    add_links(n, inputs, scenario, settings)
    add_interconnectors(n, inputs, scenario, settings)
    add_loads(n, inputs, scenario, settings)
    add_renewables(n, inputs, scenario, settings)
    add_thermal(n, inputs, scenario, settings)
    add_storage(n, inputs, scenario, settings)
    add_hydrogen_cluster(n, inputs, scenario, settings)
    add_steel_loads(n, inputs, scenario, settings)
    if scenario.co2_cap_mt is not None:
        add_co2_cap(n, scenario.co2_cap_mt)
    add_fes_capacity_ceiling(n, inputs, scenario)
    n.meta = {"scenario": scenario.model_dump(), "settings": settings.model_dump()}
    return n


def network_fingerprint(n: pypsa.Network) -> str:
    """A short hash of everything an unsolved network's LP is built from.

    Each run records it in `run_meta.json`, and a test rebuilds every committed scenario and
    compares, so a change to data, config or model code that would move a result fails CI until
    that scenario is re-solved. It covers what the network is built from, not how it is solved:
    solver options and library versions are checked against `run_meta.json` separately. Floats
    are hashed at ten significant figures so that last-bit differences between platforms rarely
    count; names and descriptions in `n.meta` are left out.
    """
    digest = hashlib.sha256()
    for c in n.components:
        if c.static.empty or c.name.endswith("Type"):
            continue
        tables = [("static", c.static), *((a, df) for a, df in c.dynamic.items() if not df.empty)]
        for attr, df in tables:
            digest.update(f"{c.name}.{attr}".encode())
            digest.update(df.to_csv(float_format="%.10g").encode())
    digest.update(n.snapshot_weightings.to_csv(float_format="%.10g").encode())
    return digest.hexdigest()[:16]
