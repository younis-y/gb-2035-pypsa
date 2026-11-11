import math

import pypsa

from gb2035.results.extract import shadow_carbon_price


def test_a_slack_cap_reports_zero_not_negative_zero():
    """A dual stored as +0.0 negates to -0.0, which the CSV writer prints as "-0"."""
    n = pypsa.Network()
    n.add("GlobalConstraint", "co2_cap", sense="<=", constant=1.0)
    for mu in (0.0, -0.0):
        n.global_constraints.loc["co2_cap", "mu"] = mu
        assert math.copysign(1.0, shadow_carbon_price(n)) == 1.0
    n.global_constraints.loc["co2_cap", "mu"] = -52.5
    assert shadow_carbon_price(n) == 52.5
