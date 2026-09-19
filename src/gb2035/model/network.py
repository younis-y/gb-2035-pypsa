"""Assemble a pypsa.Network for one scenario."""

from __future__ import annotations

from typing import Any, cast

import pandas as pd
import pypsa

from gb2035.config import Scenario, Settings
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
from gb2035.model.constraints import add_co2_cap, add_steel_loads
from gb2035.model.inputs import ModelInputs

HOURS_PER_YEAR = 8760.0


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
    n = pypsa.Network(name=f"gb2035 {scenario.name}")
    snapshots = select_snapshots(pd.DatetimeIndex(inputs.demand.index), scenario, settings)
    n.set_snapshots(cast(Any, snapshots))
    weight = HOURS_PER_YEAR / len(snapshots)
    n.snapshot_weightings.loc[:, ["objective", "generators"]] = weight
    n.snapshot_weightings.loc[:, "stores"] = float(settings.resolution_hours)
    add_carriers(n, scenario, settings)
    add_buses(n, inputs)
    add_links(n, inputs, scenario, settings)
    add_interconnectors(n, inputs, settings)
    add_loads(n, inputs, scenario, settings)
    add_renewables(n, inputs, scenario, settings)
    add_thermal(n, inputs, scenario, settings)
    add_storage(n, inputs, scenario, settings)
    add_hydrogen_cluster(n, inputs, scenario, settings)
    add_steel_loads(n, inputs, scenario, settings)
    if scenario.co2_cap_mt is not None:
        add_co2_cap(n, scenario.co2_cap_mt)
    n.meta = {"scenario": scenario.model_dump(), "settings": settings.model_dump()}
    return n
