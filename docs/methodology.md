# gb2035 methodology

## Question

What is the least-cost GB power system in 2035 as the annual CO2 cap tightens from roughly
today's emissions to near zero? How does the optimised mix compare with NESO's FES 2025
Holistic Transition? And what does an industrial hydrogen demand at Teesside do to the
answer? One linear program solves capacity expansion and hourly dispatch together, across a
sweep of CO2 caps and variants. Results live in `results/summary.csv` and the README; this
page covers only the method.

## Spatial structure

The network has 20 AC buses, from the PyPSA-GB zonal topology (inherited from
UK-Calliope): Z1_1 to Z1_4 split Shetland, the Western Isles and the Highlands; Z2 to Z17
run from North East Scotland to the South West peninsula. A 21st bus, `Teesside H2`, carries
hydrogen only, coupled to Z7. Offshore lease areas land at Z8 (Dogger Bank, Hornsea) and
Z12 (East Anglia).

31 inter-zone links join the buses as transport-model `Link`s: fixed MW, no losses, sunk and
never extendable, about 198 GW of corridor capacity in total. `cap5_tx_expansion` adds a
parallel `<corridor> new` link per corridor, extendable from zero, priced from HVDC or HVAC
cost per MW-km and distance; the existing link stays fixed and free of capital cost, so only
genuinely new MW are charged.

Interconnectors are two `Generator`s per landing bus, an import leg and an export leg,
each carrying that bus's full share of 19.4 GW (FES 2025 Holistic Transition, scaled pro
rata from the NESO register), priced separately at 65 GBP/MWh import and 45 GBP/MWh export,
so exports clear below imports as a GB surplus usually meets a surplus next door. Both legs
are price-taking up to capacity, and imports carry no territorial emissions. Because each
leg carries the full capacity, `capacities.csv` sums to 38.8 GW of interconnector generator
`p_nom` for 19.4 GW of physical capacity; only one leg can be non-zero in a given hour.

## Technologies and brownfield convention

Renewables, thermal plant and batteries split into a fixed brownfield unit (REPD or DUKES,
FOM only) and an extendable greenfield unit from zero (annuitised capex plus FOM).

| Technology | Existing (brownfield) | New build (greenfield) |
|---|---|---|
| Onshore wind, solar | REPD floor | national total, split by land area |
| Offshore wind | REPD MW per zone | three lease areas plus six coastal zones, by share |
| Nuclear, pumped hydro | Hinkley Point C + Sizewell B (4.46 GW); DUKES pumped storage; no fixed cost | not modelled |
| Existing gas | DUKES fleet, retirement only | new OCGT and gas CCS (90 percent capture) |
| Battery | REPD MW; only the inverter's FOM | 2 hour duration |

Nuclear's 4.46 GW is below FES 2025's 5.04 GW: only the two named stations are fixed.

The battery holds 2 hours at rated power, 90 percent round-trip split as the square root
each way, with a 0.09 GBP/MWh wear cost from the author's PuLP model.

The Teesside node couples to Z7 via an electrolysis link, a salt-cavern store and a turbine
link, plus a flat industrial load and an optional blue-hydrogen generator (gas reforming,
capped at 1.2 GW).

## Time and weather

Snapshots run hourly through 2035, using 2019 for wind, solar and the shape of demand,
scaled to a FES 2035 total (8,760 snapshots, weight 1). The `test` CI scenario takes one
high-demand January week (168 snapshots), weighted up to match a full year's magnitude.
`resolution_hours` can thin a year to every third hour, 2,920 snapshots weighted 3 so annual
totals stay right: a subsample, not an average.

## Carbon

A single PyPSA `GlobalConstraint` caps annual CO2 from gas, gas CCS and blue hydrogen;
nothing else emits. Its dual, read off the solved LP, is reported per scenario as the shadow
carbon price in GBP/tCO2, and it rises as the cap tightens: 0, 33, 33, 52 and 910 GBP/t at
the 30, 20, 10, 5 and 2 MtCO2 caps (`results/summary.csv`). Zero at 30 Mt means the cap is
slack, since the unconstrained optimum already emits 28.2 Mt. `uncapped` drops the constraint
and instead adds a flat 55 GBP/tCO2, the UK ETS level, to every emitting generator's marginal
cost, so its reported total includes carbon payments that are a transfer rather than a
resource cost and is not comparable with the capped scenarios.

## Costs and objective

The objective minimises annualised capital cost, fixed and variable O&M, fuel, and, in
`uncapped` only, carbon price. Capital cost per MW-year is capex times an annuity factor at
the discount rate (0.07, override-able per technology) plus fixed O&M. Costs come from
technology-data v0.15.0 for 2035, EUR to GBP at 0.85, with DESNZ Electricity Generation
Costs 2025 overriding solar, onshore and offshore wind, CCGT, OCGT, gas CCS and
hydrogen-to-power.

PyPSA prices capital cost only on extendable capacity, so the objective misses brownfield
FOM. The code adds this back after solving as `fixed_asset_cost`, so the reported total
includes the sunk fleet's cost; nuclear, pumped hydro and interconnectors still carry none,
so even that total understates the truth slightly.

## Scenarios

Scenarios are diffs against `config/settings.yaml` in `config/scenarios.yaml`. Thirteen are
defined; twelve feed the sweep, and `test` is the one-week CI check.

| Scenario | Isolates |
|---|---|
| `uncapped` | UK ETS price, no cap |
| `cap30` to `cap0p5` | CO2 sweep: 30, 20, 10, 5, 2, 0.5 MtCO2/yr (`cap0p5` did not converge; see below) |
| `cap5_no_h2` | Teesside coupling effect (demand zeroed) |
| `cap5_ee_demand` | higher demand pathway (Electric Engagement) |
| `cap5_tx_expansion` | value of extendable links |
| `cap5_import_100` | import-price sensitivity (100 vs 65 GBP/MWh) |
| `cap5_steel` | EAF loads, Port Talbot and Scunthorpe; hydrogen-DRI optional |
| `test` | one week, CI regression |

## Resolution and solver

The full sweep runs at 3-hourly resolution with HiGHS's PDLP (first-order) solver at 1e-5
feasibility tolerance. On a four-week slice, simplex took about 20 minutes to reach optimal;
scaled to a full year it did not finish within hours. Interior point without crossover was
faster on those four weeks, about three minutes, but ended at status "unknown" rather
than "optimal", since skipping crossover leaves infeasibility above HiGHS's threshold. PDLP
solved the full 3-hourly year in about 9 minutes at "optimal".

In the published sweep PDLP solved each 3-hourly year in 6 to 63 minutes, with one
exception. `cap0p5`, the 0.5 MtCO2 cap, never converged and was killed after 1 hour 50
minutes, so it is not in the results: that cap leaves only about 0.4 Mt for unabated gas once
blue hydrogen's 0.1 Mt is paid for, which puts the LP on the near-vertical part of the
abatement curve, exactly where a first-order method crawls. The sweep therefore reports 30 down to 2 MtCO2, and `cap2`
is the tightest converged cap.

PDLP satisfies constraints only to within tolerance, not at an exact vertex, so its duals
are less precise than a simplex solution's, including the shadow carbon price, and cost
differences below about 0.1 m GBP/yr on a 14.8 bn base are inside that tolerance. The
one-week harness uses simplex instead: PDLP's status was not reproducible across platforms at
this horizon, optimal on macOS, unknown on Linux CI. An hourly `cap5` run checks what
3-hourly resolution costs in accuracy: 0.4 percent on total cost, nothing on the shadow
carbon price, and about 1 GW shifted between new onshore wind and new solar.

## Known simplifications

- No BECCS: keeps carbon accounting free of negative emissions.
- No unit commitment or reserves: dispatch is a continuous LP, not mixed-integer.
- Interconnector trade is price-taking, unbounded up to capacity at a fixed price each way.
- Nuclear, pumped hydro and interconnectors carry no fixed cost, a small constant
  understatement of cost.
- East Anglia's offshore profile uses the nearest ERA5 cells the cutout covers, short of the
  real lease area.
- ERA5 overstates onshore capacity factors at a few small, coastal or island zones
  (Shetland, the Western Isles, Argyll).
- Zonal demand is split by the author's own population estimates, not an official
  GSP-level breakdown.
- The headline sweep runs 3-hourly, a subsample rather than an average, not hourly as
  designed.
- The tightest cap in the design, 0.5 MtCO2, is not in the results: PDLP did not converge on
  it within the run budget.
