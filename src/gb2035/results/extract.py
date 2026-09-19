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
            }
        )
    df = pd.DataFrame(rows)
    # Task 11 splits sunk capacity into its own fixed units; only the rest is new build.
    df["existing"] = df["name"].str.contains("_existing")
    return df


def energy(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    gen = n.generators_t.p.mul(w, axis=0).sum().groupby(n.generators["carrier"]).sum() / MWH_PER_TWH
    su = (
        n.storage_units_t.p.mul(w, axis=0)
        .clip(lower=0)
        .sum()
        .groupby(n.storage_units["carrier"])
        .sum()
        / MWH_PER_TWH
    )
    link_out = (-n.links_t.p1).mul(w, axis=0).clip(lower=0).sum().groupby(
        n.links["carrier"]
    ).sum() / MWH_PER_TWH
    out: pd.DataFrame = (
        pd.concat([gen, su, link_out.loc[link_out.index.isin(["h2_turbine", "electrolysis"])]])
        .rename("twh")
        .reset_index()
    )
    out.columns = ["carrier", "twh"]
    return out


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
    capex = n.statistics.capex().rename("gbp_per_yr").reset_index()
    capex["kind"] = "capex"
    opex = n.statistics.opex(groupby_time="sum").rename("gbp_per_yr").reset_index()
    opex["kind"] = "opex"
    df = pd.concat([capex, opex], ignore_index=True)
    tail = pd.DataFrame(
        [
            {
                "component": "fixed_assets",
                "carrier": "all",
                "gbp_per_yr": solve.fixed_asset_cost_gbp_per_yr,
                "kind": "fixed_asset_fom",
            },
            {
                "component": "total",
                "carrier": "total",
                "gbp_per_yr": solve.total_cost_gbp_per_yr,
                "kind": "total",
            },
        ]
    )
    return cast(pd.DataFrame, pd.concat([df, tail], ignore_index=True))


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
        weighted = float((price[bus] * demand * w).sum() / (demand * w).sum())
        rows.append({"metric": "demand_weighted_price_gbp_per_mwh", "zone": bus, "value": weighted})
    return pd.DataFrame(rows)


def flows(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    rows: list[dict[str, Any]] = []
    for name, link in n.links[n.links["carrier"].isin(["AC", "DC"])].iterrows():
        p = n.links_t.p0[name]
        cap = float(link["p_nom_opt"]) if link["p_nom_opt"] > 0 else float(link["p_nom"])
        rows.append(
            {
                "link": name,
                "bus0": link["bus0"],
                "bus1": link["bus1"],
                "p_nom_opt_mw": cap,
                "twh_forward": float((p.clip(lower=0) * w).sum()) / MWH_PER_TWH,
                "twh_reverse": float((-p.clip(upper=0) * w).sum()) / MWH_PER_TWH,
                "max_utilisation": float(p.abs().max() / cap) if cap > 0 else 0.0,
                "hours_congested_share": float((p.abs() >= 0.99 * cap).mean()) if cap > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def curtailment(n: pypsa.Network) -> pd.DataFrame:
    w = _weights(n)
    rows: list[dict[str, Any]] = []
    for carrier in ("onwind", "offwind", "solar"):
        gens = n.generators[n.generators["carrier"] == carrier]
        available = (
            (n.generators_t.p_max_pu[gens.index] * gens["p_nom_opt"]).mul(w, axis=0).sum().sum()
        )
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
    gen = n.generators_t.p.T.groupby(n.generators["carrier"]).sum().T
    su = n.storage_units_t.p.T.groupby(n.storage_units["carrier"]).sum().T
    out: pd.DataFrame = pd.concat([gen, su], axis=1)
    out["h2_turbine"] = -n.links_t.p1[n.links[n.links["carrier"] == "h2_turbine"].index].sum(axis=1)
    out["electrolysis"] = -n.links_t.p0[n.links[n.links["carrier"] == "electrolysis"].index].sum(
        axis=1
    )
    load = _loads(n)
    ac_buses = n.buses[n.buses["carrier"] == "AC"].index
    out["load"] = load[[c for c in n.loads.index if n.loads.at[c, "bus"] in ac_buses]].sum(axis=1)
    out["price_mean_gbp_per_mwh"] = n.buses_t.marginal_price[ac_buses].mean(axis=1)
    out.index.name = "snapshot"
    return out


def summary_row(n: pypsa.Network, scenario_name: str, solve: SolveResult) -> pd.DataFrame:
    cap = capacities(n)
    gen_gw = cap[cap["component"] == "Generator"].groupby("carrier")["p_nom_opt"].sum() / 1e3
    new_gw = cap[~cap["existing"]].groupby("carrier")["p_nom_opt"].sum() / 1e3
    em = emissions(n).set_index("carrier")["mt_co2"]
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
            cast(Any, curtailment(n).eval("(available_twh - used_twh)")).sum()
            / max(curtailment(n)["available_twh"].sum(), 1e-9)
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
            df.to_csv(path, index=False, float_format="%.6g")
        written.append(path)
    return written
