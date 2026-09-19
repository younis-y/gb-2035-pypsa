"""Add PyPSA components to a network from ModelInputs, a Scenario and Settings."""

from __future__ import annotations

import math
from typing import Any, cast

import pandas as pd
import pypsa

from gb2035.config import HydrogenSettings, Scenario, Settings
from gb2035.data.costs import annuity, battery_capital_cost_per_mw_yr, capital_cost_per_yr
from gb2035.data.demand import build_zonal_demand, demand_target_twh
from gb2035.data.zones import LAND_ZONES, zone_land_area_km2
from gb2035.model.inputs import ModelInputs, offshore_units

H2_BUS_OFFSET = 0.25


def _floor(repd: pd.DataFrame, zone: str, technology: str) -> float:
    rows = repd[(repd["zone"] == zone) & (repd["technology"] == technology)]
    return float(rows["p_nom_mw"].sum())


def _fleet(fleet: pd.DataFrame, zone: str, technology: str) -> float:
    rows = fleet[(fleet["zone"] == zone) & (fleet["technology"] == technology)]
    return float(rows["p_nom_mw"].sum())


def _carbon_adder(scenario: Scenario, co2_t_per_mwh_th: float, efficiency: float) -> float:
    price = scenario.carbon_price_gbp_t or 0.0
    return price * co2_t_per_mwh_th / efficiency


def add_carriers(n: pypsa.Network, scenario: Scenario, settings: Settings) -> None:
    residual_ccs = settings.gas_co2_t_per_mwh_th * (1.0 - settings.gas_ccs_capture_rate)
    carriers = {
        "AC": 0.0,
        "DC": 0.0,
        "H2": 0.0,
        "onwind": 0.0,
        "offwind": 0.0,
        "solar": 0.0,
        "nuclear": 0.0,
        "gas": settings.gas_co2_t_per_mwh_th,
        "gas_ccs": residual_ccs,
        "h2_turbine": 0.0,
        "battery": 0.0,
        "pumped_hydro": 0.0,
        "import": 0.0,
        "electrolysis": 0.0,
        "h2_store": 0.0,
        "blue_h2": scenario.hydrogen.blue_h2_co2_t_per_mwh,
        "load": 0.0,
    }
    n.add("Carrier", list(carriers), co2_emissions=list(carriers.values()))


def add_buses(n: pypsa.Network, inputs: ModelInputs) -> None:
    n.add(
        "Bus",
        inputs.buses.index.tolist(),
        x=inputs.buses["x"].tolist(),
        y=inputs.buses["y"].tolist(),
        carrier="AC",
        v_nom=400.0,
    )


def add_links(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    links = inputs.links
    kwargs: dict[str, Any] = {}
    if scenario.transmission_expandable:
        costs: list[float] = []
        for name, row in links.iterrows():
            km = inputs.link_distance_km.get(str(name), 100.0)
            tech = "hvdc_submarine" if row["carrier"] == "DC" else "hvac_overhead"
            c = inputs.costs.loc[tech]
            per_mw_yr = (
                annuity(settings.discount_rate, float(cast(Any, c["lifetime_yr"])))
                * float(cast(Any, c["capex_gbp"]))
                + float(cast(Any, c["fom_gbp_per_yr"]))
            ) * km
            costs.append(per_mw_yr)
        kwargs = {
            "p_nom_extendable": True,
            "p_nom_min": links["p_nom"].tolist(),
            "capital_cost": costs,
        }
    n.add(
        "Link",
        links.index.tolist(),
        bus0=links["bus0"].tolist(),
        bus1=links["bus1"].tolist(),
        carrier=links["carrier"].tolist(),
        p_nom=links["p_nom"].tolist(),
        p_min_pu=-1.0,
        efficiency=1.0,
        **kwargs,
    )


def add_interconnectors(n: pypsa.Network, inputs: ModelInputs, settings: Settings) -> None:
    ic = inputs.interconnectors
    scale = settings.interconnector_total_gw * 1000.0 / float(ic["p_nom"].sum())
    n.add(
        "Generator",
        [f"ic {name}" for name in ic.index],
        bus=ic["bus1"].tolist(),
        carrier="import",
        p_nom=(ic["p_nom"] * scale).tolist(),
        p_min_pu=-1.0,
        p_max_pu=1.0,
        marginal_cost=settings.interconnector_price_gbp_mwh,
    )


def add_loads(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    target = demand_target_twh(inputs.fes, scenario.demand_pathway, settings.losses_uplift)
    zonal = build_zonal_demand(inputs.demand, inputs.weights, target).loc[n.snapshots]
    zonal.columns = [f"load {z}" for z in zonal.columns]
    n.add(
        "Load",
        zonal.columns.tolist(),
        bus=[c.split(" ", 1)[1] for c in zonal.columns],
        carrier="load",
        p_set=zonal,
    )


def add_renewables(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    r = settings.discount_rate
    area = zone_land_area_km2(inputs.zones)
    area_share = area / area.sum()
    prof = inputs.profiles.loc[n.snapshots]
    for tech, national_gw in (
        ("onwind", inputs.caps.onwind_national_gw),
        ("solar", inputs.caps.solar_national_gw),
    ):
        names = [f"{tech} {z}" for z in LAND_ZONES]
        floors = [_floor(inputs.repd, z, tech) for z in LAND_ZONES]
        caps = [
            max(national_gw * 1000.0 * float(area_share[z]), f)
            for z, f in zip(LAND_ZONES, floors, strict=True)
        ]
        pmax = cast(pd.DataFrame, prof[tech][list(LAND_ZONES)]).copy()
        pmax.columns = names
        n.add(
            "Generator",
            names,
            bus=list(LAND_ZONES),
            carrier=tech,
            p_nom_extendable=True,
            p_nom_min=floors,
            p_nom_max=caps,
            p_max_pu=pmax,
            capital_cost=capital_cost_per_yr(inputs.costs, tech, r),
            marginal_cost=float(cast(Any, inputs.costs.at[tech, "vom_gbp_per_mwh"])),
        )
    units = offshore_units(inputs.caps)
    floor_taken: set[str] = set()
    for unit, bus, profile_zone in units:
        share = inputs.caps.offwind_shares[unit]
        cap = inputs.caps.offwind_national_gw * 1000.0 * share
        floor = 0.0
        if bus not in floor_taken:
            floor = _floor(inputs.repd, bus, "offwind")
            floor_taken.add(bus)
        n.add(
            "Generator",
            f"offwind {unit}",
            bus=bus,
            carrier="offwind",
            p_nom_extendable=True,
            p_nom_min=floor,
            p_nom_max=max(cap, floor),
            p_max_pu=prof[("offwind", profile_zone)],
            capital_cost=capital_cost_per_yr(inputs.costs, "offwind", r),
            marginal_cost=float(cast(Any, inputs.costs.at["offwind", "vom_gbp_per_mwh"])),
        )


def add_thermal(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    r = settings.discount_rate
    c = inputs.costs
    gas = settings.gas_price_gbp_mwh_th
    co2 = settings.gas_co2_t_per_mwh_th
    for z in LAND_ZONES:
        nuclear_mw = _fleet(inputs.fleet, z, "nuclear")
        if nuclear_mw > 0:
            n.add(
                "Generator",
                f"nuclear {z}",
                bus=z,
                carrier="nuclear",
                p_nom=nuclear_mw,
                p_nom_extendable=False,
                marginal_cost=settings.nuclear_marginal_cost_gbp_mwh,
                efficiency=1.0,
            )
        for tech, existing_key, eff in (
            ("ccgt", "ccgt_existing", settings.existing_ccgt_efficiency),
            ("ocgt", "ocgt", float(cast(Any, c.at["ocgt", "efficiency"]))),
        ):
            mw = _fleet(inputs.fleet, z, tech)
            if mw > 0:
                n.add(
                    "Generator",
                    f"{tech}_existing {z}",
                    bus=z,
                    carrier="gas",
                    p_nom_extendable=True,
                    p_nom_max=mw,
                    efficiency=eff,
                    capital_cost=float(cast(Any, c.at[existing_key, "fom_gbp_per_yr"])),
                    marginal_cost=gas / eff
                    + float(cast(Any, c.at[existing_key, "vom_gbp_per_mwh"]))
                    + _carbon_adder(scenario, co2, eff),
                )
        eff_ocgt = float(cast(Any, c.at["ocgt", "efficiency"]))
        n.add(
            "Generator",
            f"ocgt {z}",
            bus=z,
            carrier="gas",
            p_nom_extendable=True,
            efficiency=eff_ocgt,
            capital_cost=capital_cost_per_yr(c, "ocgt", r),
            marginal_cost=gas / eff_ocgt
            + float(cast(Any, c.at["ocgt", "vom_gbp_per_mwh"]))
            + _carbon_adder(scenario, co2, eff_ocgt),
        )
        eff_ccs = float(cast(Any, c.at["gas_ccs", "efficiency"]))
        captured_t_per_mwh_el = co2 * settings.gas_ccs_capture_rate / eff_ccs
        residual = co2 * (1.0 - settings.gas_ccs_capture_rate)
        n.add(
            "Generator",
            f"gas_ccs {z}",
            bus=z,
            carrier="gas_ccs",
            p_nom_extendable=True,
            efficiency=eff_ccs,
            capital_cost=capital_cost_per_yr(c, "gas_ccs", r),
            marginal_cost=gas / eff_ccs
            + float(cast(Any, c.at["gas_ccs", "vom_gbp_per_mwh"]))
            + settings.ccs_transport_storage_gbp_t * captured_t_per_mwh_el
            + _carbon_adder(scenario, residual, eff_ccs),
        )


def add_storage(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    eta = math.sqrt(settings.battery_round_trip_efficiency)
    bat_cost = battery_capital_cost_per_mw_yr(
        inputs.costs, settings.battery_hours, settings.discount_rate
    )
    n.add(
        "StorageUnit",
        [f"battery {z}" for z in LAND_ZONES],
        bus=list(LAND_ZONES),
        carrier="battery",
        p_nom_extendable=True,
        p_nom_min=[_floor(inputs.repd, z, "battery") for z in LAND_ZONES],
        max_hours=settings.battery_hours,
        efficiency_store=eta,
        efficiency_dispatch=eta,
        cyclic_state_of_charge=True,
        capital_cost=bat_cost,
        marginal_cost=settings.battery_wear_cost_gbp_mwh,
    )
    for z in LAND_ZONES:
        mw = _floor(inputs.repd[inputs.repd["status"] == "operational"], z, "pumped_hydro")
        if mw > 0:
            n.add(
                "StorageUnit",
                f"pumped_hydro {z}",
                bus=z,
                carrier="pumped_hydro",
                p_nom=mw,
                max_hours=8.0,
                efficiency_store=math.sqrt(0.75),
                efficiency_dispatch=math.sqrt(0.75),
                cyclic_state_of_charge=True,
            )


def add_hydrogen_node(
    n: pypsa.Network,
    name: str,
    zone: str,
    demand_twh: float,
    hydrogen: HydrogenSettings,
    inputs: ModelInputs,
    settings: Settings,
    carbon_price: float,
) -> None:
    """Electrolysis, store, turbine, optional blue supply and a flat industrial load at one zone."""
    r = settings.discount_rate
    c = inputs.costs
    bus = f"{name} H2"
    n.add(
        "Bus",
        bus,
        carrier="H2",
        x=float(cast(Any, inputs.buses.at[zone, "x"])) + H2_BUS_OFFSET,
        y=float(cast(Any, inputs.buses.at[zone, "y"])),
    )
    n.add(
        "Link",
        f"electrolysis {name}",
        bus0=zone,
        bus1=bus,
        carrier="electrolysis",
        p_nom_extendable=True,
        efficiency=hydrogen.electrolysis_efficiency,
        capital_cost=capital_cost_per_yr(c, "electrolysis", r),
    )
    n.add(
        "Store",
        f"h2_store {name}",
        bus=bus,
        carrier="h2_store",
        e_nom_extendable=True,
        e_cyclic=True,
        capital_cost=capital_cost_per_yr(c, "h2_store", r),
    )
    n.add(
        "Link",
        f"h2_turbine {name}",
        bus0=bus,
        bus1=zone,
        carrier="h2_turbine",
        p_nom_extendable=True,
        efficiency=hydrogen.turbine_efficiency,
        capital_cost=capital_cost_per_yr(c, "h2_ccgt", r) * hydrogen.turbine_efficiency,
        marginal_cost=float(cast(Any, c.at["h2_ccgt", "vom_gbp_per_mwh"]))
        * hydrogen.turbine_efficiency,
    )
    if demand_twh > 0:
        n.add("Load", f"h2_demand {name}", bus=bus, carrier="load", p_set=demand_twh * 1e6 / 8760.0)
    if hydrogen.blue_h2_enabled:
        n.add(
            "Generator",
            f"blue_h2 {name}",
            bus=bus,
            carrier="blue_h2",
            p_nom_extendable=True,
            p_nom_max=hydrogen.blue_h2_max_mw,
            efficiency=1.0,
            marginal_cost=hydrogen.blue_h2_cost_gbp_mwh
            + carbon_price * hydrogen.blue_h2_co2_t_per_mwh,
        )


def add_hydrogen_cluster(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    add_hydrogen_node(
        n,
        "Teesside",
        scenario.hydrogen.bus_zone,
        scenario.hydrogen.industrial_demand_twh,
        scenario.hydrogen,
        inputs,
        settings,
        scenario.carbon_price_gbp_t or 0.0,
    )
