"""Typed configuration: model-wide settings, scenarios and sourced assumptions."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Pathway = Literal["Holistic Transition", "Electric Engagement", "Hydrogen Evolution"]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weather_year: int = 2019
    target_year: int = 2035
    resolution_hours: int = Field(default=1, ge=1, le=24)
    discount_rate: float = Field(default=0.07, gt=0, lt=0.2)
    eur_to_gbp: float = 0.85
    losses_uplift: float = 1.07
    interconnector_total_gw: float = 19.4
    interconnector_import_price_gbp_mwh: float = 65.0
    interconnector_export_price_gbp_mwh: float = 45.0
    gas_price_gbp_mwh_th: float = 24.0
    gas_co2_t_per_mwh_th: float = 0.184
    gas_ccs_capture_rate: float = Field(default=0.90, ge=0, le=1)
    ccs_transport_storage_gbp_t: float = 9.0
    existing_ccgt_efficiency: float = 0.50
    nuclear_marginal_cost_gbp_mwh: float = 8.0
    battery_hours: float = 2.0
    battery_round_trip_efficiency: float = Field(default=0.90, gt=0, le=1)
    battery_wear_cost_gbp_mwh: float = 0.09
    pumped_hydro_hours: float = 8.0
    pumped_hydro_round_trip_efficiency: float = Field(default=0.75, gt=0, le=1)
    solver_name: str = "highs"
    solver_options: dict[str, Any] = Field(default_factory=lambda: {"output_flag": False})

    @model_validator(mode="after")
    def _exports_clear_below_imports(self) -> Settings:
        """An export price above the import price is a money pump: buy in, sell out, repeat."""
        if self.interconnector_export_price_gbp_mwh > self.interconnector_import_price_gbp_mwh:
            msg = (
                "interconnector_export_price_gbp_mwh must not exceed "
                "interconnector_import_price_gbp_mwh"
            )
            raise ValueError(msg)
        return self


class HydrogenSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bus_zone: str = "Z7"
    industrial_demand_twh: float = Field(default=5.0, ge=0)
    electrolysis_efficiency: float = Field(default=0.67, gt=0, le=1)
    turbine_efficiency: float = Field(default=0.50, gt=0, le=1)
    blue_h2_enabled: bool = False
    blue_h2_max_mw: float = 1200.0
    blue_h2_cost_gbp_mwh: float = 70.0
    blue_h2_co2_t_per_mwh: float = 0.02


class SteelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    port_talbot_eaf_twh: float = 1.5
    scunthorpe_eaf_twh: float = 1.5
    h2_dri_enabled: bool = False
    h2_dri_mt_steel: float = 3.0
    h2_kg_per_t: float = 51.0
    h2_lhv_mwh_per_t: float = 33.33
    dri_electricity_mwh_per_t: float = 0.7


class SnapshotWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: str
    end: str


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str = ""
    co2_cap_mt: float | None = Field(default=None, ge=0)
    carbon_price_gbp_t: float | None = Field(default=None, ge=0)
    demand_pathway: Pathway = "Holistic Transition"
    hydrogen: HydrogenSettings = Field(default_factory=HydrogenSettings)
    # Each overrides the matching Settings price when set; either direction may move alone
    # (the `cap5_import_100` sensitivity lifts imports and leaves exports where they are).
    interconnector_import_price_gbp_mwh: float | None = Field(default=None, ge=0)
    interconnector_export_price_gbp_mwh: float | None = Field(default=None, ge=0)
    transmission_expandable: bool = False
    steel: SteelSettings | None = None
    snapshots: SnapshotWindow | None = None
    # Merged over Settings.solver_options when set, for scenarios that need a different solver
    # (e.g. the CI test week uses simplex; see model/solve.py).
    solver_options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _cap_xor_price(self) -> Scenario:
        if self.co2_cap_mt is not None and self.carbon_price_gbp_t is not None:
            msg = "set co2_cap_mt or carbon_price_gbp_t, not both"
            raise ValueError(msg)
        return self


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float
    unit: str
    source: str = Field(min_length=1)
    confidence: Literal["published", "derived", "assumption"]
    note: str = ""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with `override` merged into `base`, recursing into nested dicts."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        doc = yaml.safe_load(fh) or {}
    if not isinstance(doc, dict):
        msg = f"{path} must contain a mapping at the top level"
        raise TypeError(msg)
    return doc


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(_read_yaml(path))


def load_assumptions(path: Path) -> dict[str, Assumption]:
    return {k: Assumption.model_validate(v) for k, v in _read_yaml(path).items()}


def list_scenarios(path: Path) -> list[str]:
    return list(_read_yaml(path).get("scenarios", {}).keys())


def load_scenario(name: str, path: Path) -> Scenario:
    doc = _read_yaml(path)
    scenarios: dict[str, Any] = doc.get("scenarios", {})
    if name not in scenarios:
        msg = f"unknown scenario {name!r}; known: {sorted(scenarios)}"
        raise KeyError(msg)
    merged = deep_merge(doc.get("defaults", {}), scenarios[name] or {})
    merged["name"] = name
    return Scenario.model_validate(merged)
