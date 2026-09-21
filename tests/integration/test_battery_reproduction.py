"""The PyPSA StorageUnit reproduces the author's PuLP arbitrage LP on a real day of prices.

PuLP formulation copied from gb-weather-to-price-forecasting/scripts/03_price_prediction_main.py
section 6.2 with the wear cost set to zero on both sides so the comparison is pure physics:
100 MW / 200 MWh, 90 percent round-trip efficiency split as sqrt on each leg, empty at the start,
no end-of-day requirement, no simultaneous charge and discharge.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pulp
import pypsa
import pytest

POWER_MW = 100.0
ENERGY_MWH = 200.0
RTE = 0.90


def pulp_profit(prices: np.ndarray) -> float:
    t_range = range(len(prices))
    eta = math.sqrt(RTE)
    prob = pulp.LpProblem("battery", pulp.LpMaximize)
    c = pulp.LpVariable.dicts("charge", t_range, 0, POWER_MW)
    d = pulp.LpVariable.dicts("discharge", t_range, 0, POWER_MW)
    s = pulp.LpVariable.dicts("soc", t_range, 0, ENERGY_MWH)
    z = pulp.LpVariable.dicts("mode", t_range, cat="Binary")
    prob += pulp.lpSum(d[t] * prices[t] - c[t] * prices[t] for t in t_range)
    for t in t_range:
        prob += c[t] <= POWER_MW * z[t]
        prob += d[t] <= POWER_MW * (1 - z[t])
        prev = 0 if t == 0 else s[t - 1]
        prob += s[t] == prev + c[t] * eta - d[t] / eta
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    return float(pulp.value(prob.objective))


def pypsa_profit(prices: np.ndarray) -> float:
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2021-03-10", periods=len(prices), freq="h"))
    n.add("Carrier", "AC")
    n.add("Bus", "grid", carrier="AC")
    n.add(
        "Generator",
        "market",
        bus="grid",
        p_nom=1e6,
        p_min_pu=-1.0,
        p_max_pu=1.0,
        marginal_cost=pd.Series(prices, index=n.snapshots),
    )
    eta = math.sqrt(RTE)
    n.add(
        "StorageUnit",
        "battery",
        bus="grid",
        p_nom=POWER_MW,
        max_hours=ENERGY_MWH / POWER_MW,
        efficiency_store=eta,
        efficiency_dispatch=eta,
        state_of_charge_initial=0.0,
        cyclic_state_of_charge=False,
    )
    status, condition = n.optimize(
        solver_name="highs", solver_options={"output_flag": False}, include_objective_constant=False
    )
    assert (status, condition) == ("ok", "optimal")
    return -float(n.objective)


def test_pypsa_matches_pulp(fixtures_dir: Path):
    prices = pd.read_csv(fixtures_dir / "prices_2021-03-10_eur.csv")["price_eur_mwh"].to_numpy()
    reference = pulp_profit(prices)
    candidate = pypsa_profit(prices)
    assert reference > 0
    assert candidate == pytest.approx(reference, rel=0.005)
