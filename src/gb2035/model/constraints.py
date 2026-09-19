"""Scenario-level constraints and optional demand blocks."""

from __future__ import annotations

import pypsa

from gb2035.config import Scenario, Settings
from gb2035.model.components import add_hydrogen_node
from gb2035.model.inputs import ModelInputs

STEEL_SITES: dict[str, tuple[str, str]] = {
    "Port Talbot": ("Z13", "port_talbot_eaf_twh"),
    "Scunthorpe": ("Z8", "scunthorpe_eaf_twh"),
}
H2_LHV_MWH_PER_T = 33.33


def add_co2_cap(n: pypsa.Network, cap_mt: float) -> None:
    n.add(
        "GlobalConstraint",
        "co2_cap",
        type="primary_energy",
        carrier_attribute="co2_emissions",
        sense="<=",
        constant=cap_mt * 1e6,
    )


def add_steel_loads(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    steel = scenario.steel
    if steel is None:
        return
    for site, (zone, field) in STEEL_SITES.items():
        twh = float(getattr(steel, field))
        if twh > 0:
            n.add("Load", f"eaf {site}", bus=zone, carrier="load", p_set=twh * 1e6 / 8760.0)
    if steel.h2_dri_enabled:
        h2_twh = steel.h2_dri_mt_steel * 1e6 * steel.h2_kg_per_t / 1000.0 * H2_LHV_MWH_PER_T / 1e6
        n.add(
            "Load",
            "dri_electricity Port Talbot",
            bus="Z13",
            carrier="load",
            p_set=steel.h2_dri_mt_steel * 1e6 * steel.dri_electricity_mwh_per_t / 8760.0,
        )
        green_only = scenario.hydrogen.model_copy(update={"blue_h2_enabled": False})
        add_hydrogen_node(
            n,
            "Port Talbot",
            "Z13",
            h2_twh,
            green_only,
            inputs,
            settings,
            scenario.carbon_price_gbp_t or 0.0,
        )
