"""Scenario-level constraints and optional demand blocks."""

from __future__ import annotations

from typing import Any, cast

import pypsa

from gb2035.config import Scenario, Settings
from gb2035.model.components import add_hydrogen_node
from gb2035.model.inputs import ModelInputs

STEEL_SITES: dict[str, tuple[str, str]] = {
    "Port Talbot": ("Z13", "port_talbot_eaf_twh"),
    "Scunthorpe": ("Z8", "scunthorpe_eaf_twh"),
}


def add_co2_cap(n: pypsa.Network, cap_mt: float) -> None:
    n.add(
        "GlobalConstraint",
        "co2_cap",
        type="primary_energy",
        carrier_attribute="co2_emissions",
        sense="<=",
        constant=cap_mt * 1e6,
    )


FES_CAPACITY_METRIC = {
    "onwind": "onshore_wind_gw",
    "solar": "solar_gw",
    "offwind": "offshore_wind_gw",
}


def add_fes_capacity_ceiling(n: pypsa.Network, inputs: ModelInputs, scenario: Scenario) -> None:
    """Hold each listed carrier's national capacity to FES 2035 for the scenario's pathway.

    A stand-in for the planning consent and land use the model has no other way to see. The
    REPD floor is already built, so the optimiser may add only the remainder, wherever it likes.
    """
    fes = inputs.fes[inputs.fes["pathway"] == scenario.demand_pathway].set_index("metric")
    for carrier in scenario.fes_capacity_ceiling:
        ceiling_mw = float(cast(Any, fes.at[FES_CAPACITY_METRIC[carrier], "value"])) * 1e3
        gens = n.generators[n.generators["carrier"] == carrier]
        existing_mw = float(gens.loc[~gens["p_nom_extendable"], "p_nom"].sum())
        if existing_mw > ceiling_mw:
            msg = f"{carrier}: {existing_mw:.0f} MW already built exceeds the FES {ceiling_mw:.0f}"
            raise ValueError(msg)
        n.add(
            "GlobalConstraint",
            f"fes_ceiling {carrier}",
            type="tech_capacity_expansion_limit",
            carrier_attribute=carrier,
            sense="<=",
            constant=ceiling_mw - existing_mw,
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
        h2_twh = (
            steel.h2_dri_mt_steel * 1e6 * steel.h2_kg_per_t / 1000.0 * steel.h2_lhv_mwh_per_t / 1e6
        )
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
