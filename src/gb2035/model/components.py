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


def _capacity(df: pd.DataFrame, zone: str, technology: str) -> float:
    """Total MW of `technology` in `zone` in a zone/technology/p_nom_mw table (REPD or fleet)."""
    rows = df[(df["zone"] == zone) & (df["technology"] == technology)]
    return float(rows["p_nom_mw"].sum())


def _existing(repd: pd.DataFrame, technology: str) -> list[tuple[str, float]]:
    """(zone, MW) for every land zone that already has capacity; zero-MW zones are dropped."""
    found = ((z, _capacity(repd, z, technology)) for z in LAND_ZONES)
    return [(z, mw) for z, mw in found if mw > 0]


def _fom(costs: pd.DataFrame, technology: str) -> float:
    """Fixed O&M only: what sunk, already-built capacity still costs to run each year."""
    return float(cast(Any, costs.at[technology, "fom_gbp_per_yr"]))


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


def add_interconnectors(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    ic = inputs.interconnectors
    scale = settings.interconnector_total_gw * 1000.0 / float(ic["p_nom"].sum())
    price = (
        scenario.interconnector_price_gbp_mwh
        if scenario.interconnector_price_gbp_mwh is not None
        else settings.interconnector_price_gbp_mwh
    )
    n.add(
        "Generator",
        [f"ic {name}" for name in ic.index],
        bus=ic["bus1"].tolist(),
        carrier="import",
        p_nom=(ic["p_nom"] * scale).tolist(),
        p_min_pu=-1.0,
        p_max_pu=1.0,
        marginal_cost=price,
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
        vom = float(cast(Any, inputs.costs.at[tech, "vom_gbp_per_mwh"]))
        # Greenfield: pure new build, annuitised capex plus FOM, capped by land-area share.
        names = [f"{tech} {z}" for z in LAND_ZONES]
        pmax = cast(pd.DataFrame, prof[tech][list(LAND_ZONES)]).copy()
        pmax.columns = names
        n.add(
            "Generator",
            names,
            bus=list(LAND_ZONES),
            carrier=tech,
            p_nom_extendable=True,
            p_nom_min=0.0,
            p_nom_max=[national_gw * 1000.0 * float(area_share[z]) for z in LAND_ZONES],
            p_max_pu=pmax,
            capital_cost=capital_cost_per_yr(inputs.costs, tech, r),
            marginal_cost=vom,
        )
        # Brownfield: the REPD floor is already built, so its capex is sunk and only FOM is paid.
        existing = _existing(inputs.repd, tech)
        if existing:
            zones = [z for z, _ in existing]
            ex_names = [f"{tech}_existing {z}" for z in zones]
            ex_pmax = cast(pd.DataFrame, prof[tech][zones]).copy()
            ex_pmax.columns = ex_names
            n.add(
                "Generator",
                ex_names,
                bus=zones,
                carrier=tech,
                p_nom=[mw for _, mw in existing],
                p_nom_extendable=False,
                p_max_pu=ex_pmax,
                capital_cost=_fom(inputs.costs, tech),
                marginal_cost=vom,
            )
    offwind_vom = float(cast(Any, inputs.costs.at["offwind", "vom_gbp_per_mwh"]))
    # Greenfield offshore: one extendable unit per configured lease area or coastal zone.
    profile_for_bus: dict[str, str] = {}
    for unit, bus, profile_zone in offshore_units(inputs.caps):
        profile_for_bus.setdefault(bus, profile_zone)
        share = inputs.caps.offwind_shares[unit]
        n.add(
            "Generator",
            f"offwind {unit}",
            bus=bus,
            carrier="offwind",
            p_nom_extendable=True,
            p_nom_min=0.0,
            p_nom_max=inputs.caps.offwind_national_gw * 1000.0 * share,
            p_max_pu=prof[("offwind", profile_zone)],
            capital_cost=capital_cost_per_yr(inputs.costs, "offwind", r),
            marginal_cost=offwind_vom,
        )
    # Brownfield offshore sits at every zone REPD gives capacity in, including the zones no
    # configured unit lands at. It takes the profile of the first unit landing there if there is
    # one, otherwise the zone's own generic offshore column.
    for zone, mw in _existing(inputs.repd, "offwind"):
        n.add(
            "Generator",
            f"offwind_existing {zone}",
            bus=zone,
            carrier="offwind",
            p_nom=mw,
            p_nom_extendable=False,
            p_max_pu=prof[("offwind", profile_for_bus.get(zone, zone))],
            capital_cost=_fom(inputs.costs, "offwind"),
            marginal_cost=offwind_vom,
        )


def add_thermal(
    n: pypsa.Network, inputs: ModelInputs, scenario: Scenario, settings: Settings
) -> None:
    r = settings.discount_rate
    c = inputs.costs
    gas = settings.gas_price_gbp_mwh_th
    co2 = settings.gas_co2_t_per_mwh_th
    for z in LAND_ZONES:
        nuclear_mw = _capacity(inputs.fleet, z, "nuclear")
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
            mw = _capacity(inputs.fleet, z, tech)
            if mw > 0:
                n.add(
                    "Generator",
                    f"{tech}_existing {z}",
                    bus=z,
                    carrier="gas",
                    p_nom_extendable=True,
                    p_nom_max=mw,
                    efficiency=eff,
                    capital_cost=_fom(c, existing_key),
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
    common: dict[str, Any] = {
        "carrier": "battery",
        "max_hours": settings.battery_hours,
        "efficiency_store": eta,
        "efficiency_dispatch": eta,
        "cyclic_state_of_charge": True,
        "marginal_cost": settings.battery_wear_cost_gbp_mwh,
    }
    n.add(
        "StorageUnit",
        [f"battery {z}" for z in LAND_ZONES],
        bus=list(LAND_ZONES),
        p_nom_extendable=True,
        p_nom_min=0.0,
        capital_cost=bat_cost,
        **common,
    )
    # Built batteries are sunk. technology-data gives no FOM for storage itself, so the inverter's
    # is the whole fixed cost of keeping them.
    existing = _existing(inputs.repd, "battery")
    if existing:
        n.add(
            "StorageUnit",
            [f"battery_existing {z}" for z, _ in existing],
            bus=[z for z, _ in existing],
            p_nom=[mw for _, mw in existing],
            p_nom_extendable=False,
            capital_cost=_fom(inputs.costs, "battery_inverter"),
            **common,
        )
    eta_ph = math.sqrt(settings.pumped_hydro_round_trip_efficiency)
    operational = inputs.repd[inputs.repd["status"] == "operational"]
    for zone, mw in _existing(operational, "pumped_hydro"):
        n.add(
            "StorageUnit",
            f"pumped_hydro {zone}",
            bus=zone,
            carrier="pumped_hydro",
            p_nom=mw,
            max_hours=settings.pumped_hydro_hours,
            efficiency_store=eta_ph,
            efficiency_dispatch=eta_ph,
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
