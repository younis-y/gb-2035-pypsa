"""Technology cost table: PyPSA technology-data in GBP with DESNZ overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd

TECHNOLOGY_DATA_MAP: dict[str, str] = {
    "onwind": "onwind",
    "offwind": "offwind",
    "solar": "solar-utility",
    "nuclear": "nuclear",
    "ccgt": "CCGT",
    "ocgt": "OCGT",
    "battery_inverter": "battery inverter",
    "battery_storage": "battery storage",
    "electrolysis": "electrolysis",
    "h2_store": "hydrogen storage underground",
    "hvdc_submarine": "HVDC submarine",
    "hvac_overhead": "HVAC overhead",
}
OVERRIDE_ONLY: tuple[str, ...] = ("ccgt_existing", "gas_ccs", "h2_ccgt")
COLUMNS = [
    "capex_gbp",
    "capex_basis",
    "fom_gbp_per_yr",
    "vom_gbp_per_mwh",
    "efficiency",
    "lifetime_yr",
    "source",
]


def annuity(rate: float, lifetime_yr: float) -> float:
    if rate <= 0:
        return 1.0 / lifetime_yr
    return float(rate / (1.0 - (1.0 + rate) ** (-lifetime_yr)))


def _basis_and_factor(unit: str, eur_to_gbp: float) -> tuple[str, float]:
    u = unit.replace(" ", "")
    if "/MW/km" in u:
        return "MW-km", eur_to_gbp
    if "/kWh" in u:
        return "MWh", 1000.0 * eur_to_gbp
    return "MW", 1000.0 * eur_to_gbp


def _from_technology_data(td: pd.DataFrame, name: str, eur_to_gbp: float) -> dict[str, object]:
    sub = td[td["technology"] == name].set_index("parameter")
    if sub.empty:
        msg = f"technology-data has no rows for {name!r}"
        raise KeyError(msg)
    inv = sub.loc["investment"]
    basis, factor = _basis_and_factor(str(inv["unit"]), eur_to_gbp)
    capex = float(cast(Any, inv["value"])) * factor
    fom_pct = float(cast(Any, sub.loc["FOM", "value"])) if "FOM" in sub.index else 0.0
    return {
        "capex_gbp": capex,
        "capex_basis": basis,
        "fom_gbp_per_yr": capex * fom_pct / 100.0,
        "vom_gbp_per_mwh": float(cast(Any, sub.loc["VOM", "value"])) * eur_to_gbp
        if "VOM" in sub.index
        else 0.0,
        "efficiency": float(cast(Any, sub.loc["efficiency", "value"]))
        if "efficiency" in sub.index
        else 1.0,
        "lifetime_yr": float(cast(Any, sub.loc["lifetime", "value"]))
        if "lifetime" in sub.index
        else 25.0,
        "source": (
            f"PyPSA technology-data v0.15.0 '{name}' ({inv['unit']}, "
            f"currency year {int(cast(Any, inv['currency_year']))}) at {eur_to_gbp} GBP/EUR"
        ),
    }


def build_costs(technology_data_csv: Path, overrides_csv: Path, eur_to_gbp: float) -> pd.DataFrame:
    td = pd.read_csv(technology_data_csv)
    rows: dict[str, dict[str, object]] = {
        t: _from_technology_data(td, n, eur_to_gbp) for t, n in TECHNOLOGY_DATA_MAP.items()
    }
    for t in OVERRIDE_ONLY:
        rows[t] = {
            "capex_gbp": 0.0,
            "capex_basis": "MW",
            "fom_gbp_per_yr": 0.0,
            "vom_gbp_per_mwh": 0.0,
            "efficiency": 1.0,
            "lifetime_yr": 25.0,
            "source": "",
        }
    ov = pd.read_csv(overrides_csv)
    for rec in ov.itertuples(index=False):
        technology = cast(str, rec.technology)
        parameter = cast(str, rec.parameter)
        if technology not in rows:
            msg = f"override for unknown technology {technology!r}"
            raise KeyError(msg)
        if parameter not in COLUMNS or parameter in ("capex_basis", "source"):
            msg = f"override parameter {parameter!r} not allowed"
            raise KeyError(msg)
        rows[technology][parameter] = float(cast(Any, rec.value))
        prior = str(rows[technology]["source"])
        new = str(rec.source)
        if new and new not in prior:
            rows[technology]["source"] = f"{prior}; {new}" if prior else new
    out = pd.DataFrame.from_dict(rows, orient="index")[COLUMNS]
    out.index.name = "technology"
    return out


def load_costs(csv: Path) -> pd.DataFrame:
    return pd.read_csv(csv).set_index("technology")


def capital_cost_per_yr(costs: pd.DataFrame, technology: str, rate: float) -> float:
    row = costs.loc[technology]
    lifetime_yr = float(cast(Any, row["lifetime_yr"]))
    capex_gbp = float(cast(Any, row["capex_gbp"]))
    fom_gbp_per_yr = float(cast(Any, row["fom_gbp_per_yr"]))
    return annuity(rate, lifetime_yr) * capex_gbp + fom_gbp_per_yr


def battery_capital_cost_per_mw_yr(costs: pd.DataFrame, hours: float, rate: float) -> float:
    inverter = capital_cost_per_yr(costs, "battery_inverter", rate)
    storage = costs.loc["battery_storage"]
    storage_lifetime_yr = float(cast(Any, storage["lifetime_yr"]))
    storage_capex_gbp = float(cast(Any, storage["capex_gbp"]))
    storage_fom_gbp_per_yr = float(cast(Any, storage["fom_gbp_per_yr"]))
    per_mwh = annuity(rate, storage_lifetime_yr) * storage_capex_gbp + storage_fom_gbp_per_yr
    return inverter + hours * per_mwh
