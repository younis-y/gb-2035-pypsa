"""Bundle every derived table the network builder needs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from gb2035.data.costs import load_costs
from gb2035.data.demand import load_zone_weights
from gb2035.data.fes import load_fes
from gb2035.data.profiles import load_profiles
from gb2035.data.zones import OFFSHORE_LANDING, OFFSHORE_ZONES, load_zones
from gb2035.paths import ProjectPaths


class RenewableCaps(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    onwind_national_gw: float
    solar_national_gw: float
    offwind_national_gw: float
    offwind_shares: dict[str, float]

    @model_validator(mode="after")
    def _shares_sum_to_one(self) -> RenewableCaps:
        total = sum(self.offwind_shares.values())
        if abs(total - 1.0) > 1e-6:
            msg = f"offwind_shares must sum to 1, got {total}"
            raise ValueError(msg)
        return self


@dataclass(frozen=True)
class ModelInputs:
    zones: gpd.GeoDataFrame
    buses: pd.DataFrame
    links: pd.DataFrame
    interconnectors: pd.DataFrame
    link_distance_km: dict[str, float]
    fleet: pd.DataFrame
    repd: pd.DataFrame
    demand: pd.Series
    weights: pd.Series
    profiles: pd.DataFrame
    costs: pd.DataFrame
    fes: pd.DataFrame
    caps: RenewableCaps


def _link_distances(yaml_path: Path) -> dict[str, float]:
    doc = yaml.safe_load(yaml_path.read_text())
    out: dict[str, float] = {}
    for key, body in doc.get("links", {}).items():
        a, b = (s.strip() for s in key.split(","))
        for tech in body.get("techs", {}).values():
            if "distance" in tech:
                km = float(tech["distance"]) * 100.0
                out[f"{a}-{b}"] = km
                out[f"{b}-{a}"] = km
    return out


def offshore_units(caps: RenewableCaps) -> list[tuple[str, str, str]]:
    """(unit name, landing bus, profile zone) for every offshore generator."""
    units: list[tuple[str, str, str]] = []
    for unit in caps.offwind_shares:
        bus = OFFSHORE_LANDING[unit] if unit in OFFSHORE_ZONES else unit
        units.append((unit, bus, unit))
    return units


def load_inputs(paths: ProjectPaths) -> ModelInputs:
    d = paths.data_derived
    buses = pd.read_csv(d / "buses.csv").set_index("name")
    links_all = pd.read_csv(d / "links.csv")
    inter_zone = links_all[
        links_all["bus0"].str.startswith("Z") & links_all["bus1"].str.startswith("Z")
    ]
    future = pd.read_csv(d / "links_future.csv").set_index("name")
    interconnectors = future[future["bus1"].str.startswith("Z")][["bus1", "p_nom"]]
    demand = pd.read_parquet(d / "demand_2019_hourly.parquet")["gross_demand_mw"]
    caps = RenewableCaps.model_validate(
        yaml.safe_load((paths.config / "renewable_caps.yaml").read_text())
    )
    return ModelInputs(
        zones=load_zones(d / "zones.geojson"),
        buses=buses,
        links=inter_zone.set_index("name"),
        interconnectors=interconnectors,
        link_distance_km=_link_distances(d / "transmission_grid_2030.yaml"),
        fleet=pd.read_csv(d / "fleet_by_zone.csv"),
        repd=pd.read_csv(d / "repd_by_zone.csv"),
        demand=demand,
        weights=load_zone_weights(paths.config / "demand_weights.csv"),
        profiles=load_profiles(d / "cf_2019_zonal.parquet"),
        costs=load_costs(d / "costs_2035_gb.csv"),
        fes=load_fes(d / "fes2025_gb_2035.csv"),
        caps=caps,
    )
