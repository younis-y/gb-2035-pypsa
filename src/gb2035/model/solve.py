"""Solve a network with HiGHS and report status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pypsa

from gb2035.config import Scenario, Settings, deep_merge


class SolveError(RuntimeError):
    """The solver did not return an optimal solution."""


def fixed_asset_cost_gbp_per_yr(n: pypsa.Network) -> float:
    """Annual fixed cost of capacity the LP never prices.

    PyPSA puts `capital_cost` in the objective only for extendable components, so any cost carried
    by a fixed one is real money the objective cannot see. This sums `capital_cost x capacity` over
    every non-extendable Generator, StorageUnit, Link and Store. Today only the `*_existing` units
    contribute: pre-existing nuclear, pumped hydro and the interconnectors are fixed too, but were
    given no capital cost, and so add nothing.
    """
    total = 0.0
    for df, nom in (
        (n.generators, "p_nom"),
        (n.storage_units, "p_nom"),
        (n.links, "p_nom"),
        (n.stores, "e_nom"),
    ):
        fixed = df[~df[f"{nom}_extendable"]]
        total += float(cast(Any, (fixed["capital_cost"] * fixed[nom]).sum()))
    return total


@dataclass(frozen=True)
class SolveResult:
    status: str
    condition: str
    objective: float
    objective_constant: float
    fixed_asset_cost_gbp_per_yr: float
    solver: str

    @property
    def lp_objective_gbp_per_yr(self) -> float:
        return self.objective + self.objective_constant

    @property
    def total_cost_gbp_per_yr(self) -> float:
        return self.lp_objective_gbp_per_yr + self.fixed_asset_cost_gbp_per_yr


def solve(n: pypsa.Network, settings: Settings, scenario: Scenario | None = None) -> SolveResult:
    """Solve with `settings.solver_options`, merging `scenario.solver_options` over it when set.

    Some scenarios need a different HiGHS solver than the settings default: the one-week `test`
    scenario pins simplex because PDLP's termination status is not deterministic across platforms
    at that horizon (optimal on macOS ARM64, "unknown" on Linux x86_64 CI, for the same inputs).
    """
    options = settings.solver_options
    if scenario is not None and scenario.solver_options:
        options = deep_merge(dict(settings.solver_options), scenario.solver_options)
    status, condition = n.optimize(
        solver_name=settings.solver_name,
        solver_options=dict(options),
        include_objective_constant=False,
    )
    if status != "ok" or condition != "optimal":
        msg = f"solve failed: status={status} condition={condition}"
        raise SolveError(msg)
    constant = float(getattr(n, "objective_constant", 0.0) or 0.0)
    return SolveResult(
        status=str(status),
        condition=str(condition),
        objective=float(cast(Any, n.objective)),
        objective_constant=constant,
        fixed_asset_cost_gbp_per_yr=fixed_asset_cost_gbp_per_yr(n),
        solver=str(options.get("solver", "default")),
    )
