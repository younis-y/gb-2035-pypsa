"""Turn a solved network into small, committed tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd
import pypsa

from gb2035.model.solve import SolveResult

MWH_PER_TWH = 1e6


def shadow_carbon_price(n: pypsa.Network) -> float:
    if "co2_cap" not in n.global_constraints.index:
        return 0.0
    mu = float(n.global_constraints.at["co2_cap", "mu"])
    return max(-mu, 0.0)


def _weights(n: pypsa.Network) -> pd.Series:
    return pd.Series(n.snapshot_weightings["generators"])


def _loads(n: pypsa.Network) -> pd.DataFrame:
    """Every load over every snapshot: constant `p_set` values live in the static table."""
    return pd.DataFrame(n.get_switchable_as_dense("Load", "p_set"))


def _zone_of(bus: str) -> str:
    return bus.replace(" H2", "")


def _is_existing(name: Any, extendable: Any) -> bool:
    """Sunk capacity, either way it can arise.

    Task 11 splits brownfield renewables and batteries into named `*_existing` units, which stay
    extendable only where the fleet is allowed to retire (`ccgt_existing`, `ocgt_existing`).
    Everything the LP cannot build — nuclear, pumped hydro, interconnectors, the fixed grid — is
    equally already there. Only what the optimiser is free to add counts as new build.
    """
    return "_existing" in str(name) or not bool(extendable)


def capacities(n: pypsa.Network) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, g in n.generators.iterrows():
        rows.append(
            {
                "component": "Generator",
                "name": name,
                "carrier": g["carrier"],
                "zone": _zone_of(g["bus"]),
                "p_nom_opt": float(g["p_nom_opt"]),
                "p_nom_min": float(g["p_nom_min"]),
                "unit": "MW",
                "existing": _is_existing(name, g["p_nom_extendable"]),
            }
        )
    for name, s in n.storage_units.iterrows():
        rows.append(
            {
                "component": "StorageUnit",
                "name": name,
                "carrier": s["carrier"],
                "zone": _zone_of(s["bus"]),
                "p_nom_opt": float(s["p_nom_opt"]),
                "p_nom_min": float(s["p_nom_min"]),
                "unit": "MW",
                "existing": _is_existing(name, s["p_nom_extendable"]),
            }
        )
    for name, link in n.links.iterrows():
        rows.append(
            {
                "component": "Link",
                "name": name,
                "carrier": link["carrier"],
                "zone": f"{link['bus0']}->{link['bus1']}",
                "p_nom_opt": float(link["p_nom_opt"]),
                "p_nom_min": float(link["p_nom_min"]),
                "unit": "MW",
                "existing": _is_existing(name, link["p_nom_extendable"]),
            }
        )
    for name, s in n.stores.iterrows():
        rows.append(
            {
                "component": "Store",
                "name": name,
                "carrier": s["carrier"],
                "zone": _zone_of(s["bus"]),
                "p_nom_opt": float(s["e_nom_opt"]),
                "p_nom_min": float(s["e_nom_min"]),
                "unit": "MWh",
                "existing": _is_existing(name, s["e_nom_extendable"]),
            }
        )
    return pd.DataFrame(rows)


def _bus_carrier(n: pypsa.Network, df: pd.DataFrame) -> pd.Series:
    """Which commodity a component's rows are denominated in, read off its bus."""
    out = pd.Series(df["bus"].map(n.buses["carrier"]))
    out.name = "bus_carrier"
    return out


def energy(n: pypsa.Network) -> pd.DataFrame:
    """Annual energy by carrier, each row labelled with the commodity it is measured in.

    `blue_h2` is hydrogen, not electricity, so it must not be added to the power rows. The
    `electrolysis` row is the electricity the electrolysers draw, carried negative to mark it as
    consumption; `h2_turbine` is the electricity they give back.
    """
    w = _weights(n)
    gen = (
        n.generators_t.p.mul(w, axis=0)
        .sum()
        .groupby([n.generators["carrier"], _bus_carrier(n, n.generators)])
        .sum()
        / MWH_PER_TWH
    )
    su = (
        n.storage_units_t.p.mul(w, axis=0)
        .clip(lower=0)
        .sum()
        .groupby([n.storage_units["carrier"], _bus_carrier(n, n.storage_units)])
        .sum()
        / MWH_PER_TWH
    )
    out: pd.DataFrame = pd.concat([gen, su]).rename("twh").reset_index()
    turbines = n.links.index[n.links["carrier"] == "h2_turbine"]
    electrolysers = n.links.index[n.links["carrier"] == "electrolysis"]
    link_rows: list[dict[str, Any]] = []
    if len(turbines):
        delivered = float((-n.links_t.p1[turbines]).mul(w, axis=0).sum().sum())
        link_rows.append(
            {"carrier": "h2_turbine", "bus_carrier": "AC", "twh": delivered / MWH_PER_TWH}
        )
    if len(electrolysers):
        drawn = float(n.links_t.p0[electrolysers].mul(w, axis=0).sum().sum())
        link_rows.append(
            {"carrier": "electrolysis", "bus_carrier": "AC", "twh": -drawn / MWH_PER_TWH}
        )
    if link_rows:
        out = pd.concat([out, pd.DataFrame(link_rows)], ignore_index=True)
    return out[["carrier", "bus_carrier", "twh"]]


def emissions(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    rows: list[dict[str, Any]] = []
    for carrier, co2 in n.carriers["co2_emissions"].items():
        if co2 <= 0:
            continue
        gens = n.generators[n.generators["carrier"] == carrier]
        if gens.empty:
            continue
        fuel_mwh = (n.generators_t.p[gens.index] / gens["efficiency"]).mul(w, axis=0).sum().sum()
        rows.append({"carrier": carrier, "mt_co2": float(fuel_mwh) * float(co2) / 1e6})
    df = pd.DataFrame(rows, columns=["carrier", "mt_co2"])
    return pd.concat(
        [df, pd.DataFrame([{"carrier": "total", "mt_co2": df["mt_co2"].sum()}])], ignore_index=True
    )


def costs(n: pypsa.Network, solve: SolveResult) -> pd.DataFrame:
    """Annual cost by component and carrier, plus memo rows.

    The `capex` and `opex` rows are the additive breakdown and sum to the total on their own:
    `statistics.capex()` already prices the sunk `*_existing` units the LP objective leaves out.
    The memo rows say how that total splits between what the solver minimised and the fixed O&M it
    could not see, so they must not be added to the component rows.
    """
    capex = n.statistics.capex().rename("gbp_per_yr").reset_index()
    capex["kind"] = "capex"
    opex = n.statistics.opex(groupby_time="sum").rename("gbp_per_yr").reset_index()
    opex["kind"] = "opex"
    df = pd.concat([capex, opex], ignore_index=True)
    df["is_memo"] = False
    df["note"] = ""
    memo = pd.DataFrame(
        [
            {
                "component": "memo",
                "carrier": "all",
                "gbp_per_yr": solve.lp_objective_gbp_per_yr,
                "kind": "memo_lp_objective",
            },
            {
                "component": "memo",
                "carrier": "all",
                "gbp_per_yr": solve.fixed_asset_cost_gbp_per_yr,
                "kind": "memo_fixed_asset_fom",
            },
            {
                "component": "memo",
                "carrier": "all",
                "gbp_per_yr": solve.total_cost_gbp_per_yr,
                "kind": "total",
            },
        ]
    )
    memo["is_memo"] = True
    memo["note"] = "not additive with component rows"
    return cast(pd.DataFrame, pd.concat([df, memo], ignore_index=True))


def duals(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    load = _loads(n)
    price = n.buses_t.marginal_price
    rows: list[dict[str, Any]] = [
        {"metric": "shadow_carbon_price_gbp_per_t", "zone": "GB", "value": shadow_carbon_price(n)}
    ]
    for bus in n.buses.index:
        loads_here = [c for c in load.columns if n.loads.at[c, "bus"] == bus]
        if not loads_here:
            continue
        demand = load[loads_here].sum(axis=1)
        weight = float((demand * w).sum())
        if weight <= 0:
            continue
        weighted = float((price[bus] * demand * w).sum() / weight)
        rows.append({"metric": "demand_weighted_price_gbp_per_mwh", "zone": bus, "value": weighted})
    return pd.DataFrame(rows)


def flows(n: pypsa.Network) -> pd.DataFrame:
    """One row per inter-zone corridor: sunk capacity, new build, and the flow over both.

    Under `transmission_expandable` a corridor is two parallel links, the fixed `{name}` and the
    extendable `{name} new`. They are one route, so their capacities add and their flows sum
    before utilisation is measured against the total.
    """
    w = _weights(n)
    tx = n.links[n.links["carrier"].isin(["AC", "DC"])]
    rows: list[dict[str, Any]] = []
    for name in (c for c in tx.index if not str(c).endswith(" new")):
        link = tx.loc[name]
        members = [name]
        new_mw = 0.0
        expansion = f"{name} new"
        if expansion in tx.index:
            members.append(expansion)
            new_mw = float(tx.at[expansion, "p_nom_opt"])
        existing_mw = float(link["p_nom"])
        cap = existing_mw + new_mw
        p = n.links_t.p0[members].sum(axis=1)
        rows.append(
            {
                "link": name,
                "bus0": link["bus0"],
                "bus1": link["bus1"],
                "p_nom_existing_mw": existing_mw,
                "p_nom_new_mw": new_mw,
                "p_nom_total_mw": cap,
                "twh_forward": float((p.clip(lower=0) * w).sum()) / MWH_PER_TWH,
                "twh_reverse": float((-p.clip(upper=0) * w).sum()) / MWH_PER_TWH,
                "max_utilisation": float(p.abs().max() / cap) if cap > 0 else 0.0,
                "hours_congested_share": float((p.abs() >= 0.99 * cap).mean()) if cap > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def curtailment(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    p_max_pu = pd.DataFrame(n.get_switchable_as_dense("Generator", "p_max_pu"))
    rows: list[dict[str, Any]] = []
    for carrier in ("onwind", "offwind", "solar"):
        gens = n.generators[n.generators["carrier"] == carrier]
        available = (p_max_pu[gens.index] * gens["p_nom_opt"]).mul(w, axis=0).sum().sum()
        used = n.generators_t.p[gens.index].mul(w, axis=0).sum().sum()
        rows.append(
            {
                "carrier": carrier,
                "available_twh": available / MWH_PER_TWH,
                "used_twh": used / MWH_PER_TWH,
                "curtailed_share": float((available - used) / available) if available > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def hydrogen(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    load = _loads(n)
    rows: list[dict[str, Any]] = []
    for link in n.links[n.links["carrier"] == "electrolysis"].index:
        name = link.split(" ", 1)[1]
        p_in = n.links_t.p0[link]
        cap = float(n.links.at[link, "p_nom_opt"])
        h2_out = float((-n.links_t.p1[link] * w).sum()) / MWH_PER_TWH
        rows += [
            {"node": name, "metric": "electrolysis_mw", "value": cap},
            {
                "node": name,
                "metric": "electrolysis_utilisation",
                "value": float((p_in * w).sum() / (cap * w.sum())) if cap > 0 else 0.0,
            },
            {"node": name, "metric": "green_h2_twh", "value": h2_out},
            {
                "node": name,
                "metric": "h2_store_mwh",
                "value": float(n.stores.at[f"h2_store {name}", "e_nom_opt"]),
            },
            {
                "node": name,
                "metric": "h2_turbine_mw_h2_input",
                "value": float(n.links.at[f"h2_turbine {name}", "p_nom_opt"]),
            },
            {
                "node": name,
                "metric": "h2_to_power_twh_el",
                "value": float((-n.links_t.p1[f"h2_turbine {name}"] * w).sum()) / MWH_PER_TWH,
            },
        ]
        blue = f"blue_h2 {name}"
        if blue in n.generators.index:
            rows.append(
                {
                    "node": name,
                    "metric": "blue_h2_twh",
                    "value": float((n.generators_t.p[blue] * w).sum()) / MWH_PER_TWH,
                }
            )
        demand = f"h2_demand {name}"
        if demand in n.loads.index:
            rows.append(
                {
                    "node": name,
                    "metric": "industrial_demand_twh",
                    "value": float((load[demand] * w).sum()) / MWH_PER_TWH,
                }
            )
    return pd.DataFrame(rows, columns=["node", "metric", "value"])


def dispatch_hourly(n: pypsa.Network) -> pd.DataFrame:
    """Hourly electricity in MW, every column on the AC system.

    Generators on the hydrogen bus are left out: their MW are hydrogen. Injections are positive and
    withdrawals negative, so every column but `load` and the price adds up to `load`.
    """
    ac_buses = n.buses[n.buses["carrier"] == "AC"].index
    ac_gens = n.generators[n.generators["bus"].isin(ac_buses)]
    gen = n.generators_t.p[ac_gens.index].T.groupby(ac_gens["carrier"]).sum().T
    su = n.storage_units_t.p.T.groupby(n.storage_units["carrier"]).sum().T
    out: pd.DataFrame = pd.concat([gen, su], axis=1)
    out["h2_turbine"] = -n.links_t.p1[n.links[n.links["carrier"] == "h2_turbine"].index].sum(axis=1)
    out["electrolysis"] = -n.links_t.p0[n.links[n.links["carrier"] == "electrolysis"].index].sum(
        axis=1
    )
    load = _loads(n)
    out["load"] = load[[c for c in n.loads.index if n.loads.at[c, "bus"] in ac_buses]].sum(axis=1)
    out["price_mean_gbp_per_mwh"] = n.buses_t.marginal_price[ac_buses].mean(axis=1)
    out.index.name = "snapshot"
    return out


def summary_row(n: pypsa.Network, scenario_name: str, solve: SolveResult) -> pd.DataFrame:
    cap = capacities(n)
    gen_gw = cap[cap["component"] == "Generator"].groupby("carrier")["p_nom_opt"].sum() / 1e3
    new_gw = cap[~cap["existing"]].groupby("carrier")["p_nom_opt"].sum() / 1e3
    curt = curtailment(n)
    em = emissions(n).set_index("carrier")["mt_co2"]
    # The export row is negative, so adding the two gives GB's net position on the wires.
    twh = energy(n).groupby("carrier")["twh"].sum()
    h2 = hydrogen(n)
    green = float(h2[(h2["node"] == "Teesside") & (h2["metric"] == "green_h2_twh")]["value"].sum())
    blue = float(h2[(h2["node"] == "Teesside") & (h2["metric"] == "blue_h2_twh")]["value"].sum())
    row = {
        "scenario": scenario_name,
        "total_cost_gbp_bn_per_yr": solve.total_cost_gbp_per_yr / 1e9,
        "lp_objective_gbp_bn_per_yr": solve.lp_objective_gbp_per_yr / 1e9,
        "fixed_asset_cost_gbp_bn_per_yr": solve.fixed_asset_cost_gbp_per_yr / 1e9,
        "shadow_carbon_price_gbp_per_t": shadow_carbon_price(n),
        "emissions_mt": float(em.get("total", 0.0)),
        "net_imports_twh": float(twh.get("import", 0.0)) + float(twh.get("export", 0.0)),
        "onwind_gw": float(gen_gw.get("onwind", 0.0)),
        "offwind_gw": float(gen_gw.get("offwind", 0.0)),
        "solar_gw": float(gen_gw.get("solar", 0.0)),
        "gas_gw": float(gen_gw.get("gas", 0.0)),
        "gas_ccs_gw": float(gen_gw.get("gas_ccs", 0.0)),
        "nuclear_gw": float(gen_gw.get("nuclear", 0.0)),
        "battery_gw": float(cap[cap["carrier"] == "battery"]["p_nom_opt"].sum() / 1e3),
        "onwind_new_gw": float(new_gw.get("onwind", 0.0)),
        "offwind_new_gw": float(new_gw.get("offwind", 0.0)),
        "solar_new_gw": float(new_gw.get("solar", 0.0)),
        "battery_new_gw": float(new_gw.get("battery", 0.0)),
        "electrolysis_gw": float(cap[cap["carrier"] == "electrolysis"]["p_nom_opt"].sum() / 1e3),
        "h2_store_gwh": float(cap[cap["carrier"] == "h2_store"]["p_nom_opt"].sum() / 1e3),
        "h2_turbine_gw_el": float(
            (
                n.links[n.links["carrier"] == "h2_turbine"]["p_nom_opt"]
                * n.links[n.links["carrier"] == "h2_turbine"]["efficiency"]
            ).sum()
            / 1e3
        ),
        "teesside_green_h2_twh": green,
        "teesside_blue_h2_twh": blue,
        "curtailed_share_wind_solar": float(
            (curt["available_twh"] - curt["used_twh"]).sum()
            / max(float(curt["available_twh"].sum()), 1e-9)
        ),
    }
    return pd.DataFrame([row])


def extract_all(
    n: pypsa.Network, scenario_name: str, solve: SolveResult
) -> dict[str, pd.DataFrame]:
    return {
        "capacities": capacities(n),
        "energy": energy(n),
        "emissions": emissions(n),
        "costs": costs(n, solve),
        "duals": duals(n),
        "flows": flows(n),
        "curtailment": curtailment(n),
        "hydrogen": hydrogen(n),
        "dispatch_hourly": dispatch_hourly(n),
        "summary_row": summary_row(n, scenario_name, solve),
    }


def write_results(results: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key, df in results.items():
        if key == "dispatch_hourly":
            path = out_dir / "dispatch_hourly.parquet"
            df.to_parquet(path)
        else:
            path = out_dir / f"{key}.csv"
            # Pounds per year run to ten digits; %.6g would publish them in scientific notation.
            df.to_csv(path, index=False, float_format="%.2f" if key == "costs" else "%.6g")
        written.append(path)
    return written
