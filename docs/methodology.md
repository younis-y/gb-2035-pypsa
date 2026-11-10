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

Each interconnector becomes two `Generator`s at its landing bus, an import leg and an export
leg, and each leg carries that interconnector's full capacity, scaled pro rata so the fleet
sums to 19.4 GW (FES 2025 Holistic Transition, from the NESO register). A landing bus that
hosts more than one interconnector therefore carries more than one pair. The legs are priced
separately at 65 GBP/MWh import and 45 GBP/MWh export, so exports clear below imports as a GB
surplus usually meets a surplus next door. Both are price-taking up to capacity, and imports
carry no territorial emissions. Because each leg carries the full capacity, `capacities.csv`
sums to 38.8 GW of interconnector generator `p_nom` for 19.4 GW of physical capacity. Nothing
stops a pair running in both directions at once: it simply never pays to, because buying at
65 to sell at 45 loses 20 GBP/MWh. That is an economic consequence of the price spread, not a
modelled constraint, and it would need one if the prices were ever set the other way up.

## Technologies and brownfield convention

Renewables, thermal plant and batteries split into a fixed brownfield unit (REPD or DUKES,
FOM only) and an extendable greenfield unit from zero (annuitised capex plus FOM).

| Technology | Existing (brownfield) | New build (greenfield) |
|---|---|---|
| Onshore wind, solar | REPD floor | national total, split by land area |
| Offshore wind | REPD MW per zone | three lease areas plus six coastal zones, by share |
| Nuclear, pumped hydro | Hinkley Point C + Sizewell B (4.46 GW); DUKES pumped storage; FOM only | not modelled |
| Existing gas | DUKES fleet, retirement only | new OCGT everywhere; gas CCS (90 percent capture) only in CCUS-cluster zones |
| Battery | REPD MW; only the inverter's FOM | 2 hour duration |

Nuclear's 4.46 GW is below FES 2025's 5.04 GW: only the two named stations are fixed.

The greenfield caps in `config/renewable_caps.yaml` are national (60 GW onshore, 150 GW
solar, 150 GW offshore), but they are applied zonally: onshore and solar are split across the
twenty land zones by land area and each zone's extendable unit gets that share as its
`p_nom_max`, while offshore is split by the named lease-area and coastal shares. Existing
REPD capacity never counts against a cap, because it sits in a separate fixed unit. The
consequence is that a national total can stay well short of its cap while individual zones
are exhausted: at `cap2` the model builds 27.7 GW of new onshore against the 60 GW national
cap, and yet 10 of the 20 onshore zones are at their land-area share to the megawatt. The
zonal caps, not the national ones, are what push the model into progressively worse sites.

The battery holds 2 hours at rated power, 90 percent round-trip split as the square root
each way, with a 0.09 GBP/MWh wear cost from the author's PuLP model.

Gas CCS is offered only where a CO2 pipeline could reach it: the six zones listed in
`config/ccs_zones.yaml` (Z7 Teesside and Z8 Humber for the East Coast Cluster, Z9 Merseyside
and North Wales for HyNet, Z5 Grangemouth for Acorn, and Z13 South Wales and Z16 Solent as
Track-2 candidates). Unrestricted, the optimiser smeared sub-100 MW lumps of CCS across all
twenty zones, Shetland and the Western Isles included, purely to shave transmission.

The Teesside node couples to Z7 via an electrolysis link, a salt-cavern store and a turbine
link, plus a flat industrial load and an optional blue-hydrogen generator (gas reforming,
capped at 1.2 GW).

## Time and weather

Snapshots are 2019 timestamps, the weather and demand year, standing for 2035: the model
carries no 2035 calendar. Wind, solar and the shape of demand all come from 2019, with demand
rescaled to a FES 2035 pathway total (8,760 snapshots, weight 1).

A scenario can name another `weather_year`, and then wind, solar and the demand shape all
come from that year instead, with demand rescaled to the same FES total. The `cap5_wy<year>`
family re-solves `cap5` on every year the Zenodo cutout record holds, 2010 to 2024, into
`results_weather_years/`. Each year's profiles come from the same `gb2035 build-profiles`
run over that year's cutout, and each year's demand from that year's NESO file. Regenerating
2019 the same way reproduced the committed `cf_2019_zonal.parquet` bit for bit when this was
built (the cutouts are not committed, so that check is a build-time observation). The
2020 and 2021 demand shapes carry lockdown, which the rescaling to a FES total does not
remove; they are kept, and flagged, rather than dropped, so the set of years is the whole
record and not a selection. Each year is solved on its own: there is no multi-year
optimisation, so no year has to be survivable on another year's build. Snapshot weights
always sum to an 8,760-hour year, so a leap year's 8,784 hours are weighted down to it, and
demand is scaled by its mean hour so that every year meets the same FES total (scaling by the
year's sum, as the first version did, left leap years 0.27 percent short; the committed-results
energy-balance test caught it). The `test` CI scenario takes one
high-demand January week (168 snapshots), weighted up to match a full year's magnitude.
`resolution_hours` can thin a year to every third hour, 2,920 snapshots weighted 3 so annual
totals stay right: a subsample, not an average.

## Planning limits, as a sensitivity

The model has no planning consent, land use or public acceptability, which is the stated
reason its answer differs from FES. `fes_capacity_ceiling` stands in for them: it holds a
carrier's national capacity, brownfield plus greenfield, to its FES 2035 figure for the
scenario's pathway, as a PyPSA `tech_capacity_expansion_limit` over the greenfield units with
the REPD floor netted off. The ceiling is national, so where the capacity goes is still the
model's choice. `cap5_fes_ceiling` and `cap2_fes_ceiling` hold onshore wind to 38.4 GW and
solar to 61.8 GW (FES 2025 Holistic Transition), and `duals.csv` reports what one more MW
under each ceiling would be worth (`fes_ceiling_rent_gbp_per_mw_yr`).

## Breakeven: how far an unbuilt technology is from entering

Every run writes `breakeven.csv`: for each extendable generator and link, one megawatt's
`market_value_gbp_per_mw_yr`, its annual margin over its own running cost at the solved nodal
prices with CO2 charged at the cap's shadow price, beside its `capital_cost_gbp_per_mw_yr`,
annuitised capex plus fixed O&M. An unbuilt unit is short of entering by the gap between the
two; a built unit earns its cost exactly unless a cap holds it back, and the excess is then
that cap's rent. Storage is left out, since its value depends on how it would cycle.

The first version read the duals of the capacity bounds instead, and the first full-year solve
showed why that fails: for every unbuilt offshore unit PDLP returned a bound dual of zero. An
unbuilt unit's dispatch is pinned at zero from both sides, so its bound dual is degenerate,
and any value from zero to the true shortfall is optimal; simplex happened to return the
shortfall, which is why a test on the simplex-solved CI week had passed. Nodal prices are far
better determined than those duals, and `network.nc` stores them, so `gb2035 extract` can
rebuild the table from a saved solve (`network.nc` is not committed, so only where the solve
was run).

A price-based breakeven is a first-order statement, so it is tested by re-solving. On the CI
week, cutting offshore capex 15 percent past the shortfall builds Dogger Bank and stopping 15
percent short builds nothing; on the full 2019 year, `cap5_offwind_capex64` and
`cap5_offwind_capex51` do the same. `tests/results/` also checks the zero-profit conditions
on every committed run (built units earn their cost, capped units at least that, unbuilt
units no more), which PDLP's solutions meet to within 6e-4 of the dearest unit's cost.

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
the discount rate (0.07, one rate for every technology) plus fixed O&M. Lifetimes, not the
rate, are what vary per technology: 38 years for solar, 35 for onshore wind, 30 for offshore,
40 for nuclear and the grid, 25 for gas. Costs come from technology-data v0.15.0 for 2035,
EUR to GBP at 0.85, with DESNZ Electricity Generation Costs 2025 overriding solar, onshore
and offshore wind, CCGT, OCGT, gas CCS and hydrogen-to-power.

PyPSA prices capital cost only on extendable capacity, so the objective misses brownfield
FOM. The code adds this back after solving as `fixed_asset_cost`, so the reported total
includes the sunk fleet's cost, nuclear and pumped hydro included. The interconnectors and
the built grid still carry none, so even that total understates the truth slightly.

## Scenarios

Scenarios are diffs against `config/settings.yaml` in `config/scenarios.yaml`. `test` is the
one-week CI check; the `cap5_wy<year>` family writes to `results_weather_years/`; everything
else feeds the main sweep in `results/`.

| Scenario | Isolates |
|---|---|
| `uncapped` | UK ETS price, no cap |
| `cap30` to `cap0p5` | CO2 sweep: 30, 20, 10, 5, 2, 0.5 MtCO2/yr (`cap0p5` did not converge; see below) |
| `cap5_no_h2` | Teesside coupling effect (demand zeroed) |
| `cap5_ee_demand` | higher demand pathway (Electric Engagement) |
| `cap5_tx_expansion` | value of extendable links |
| `cap5_import_100` | import-price sensitivity (100 vs 65 GBP/MWh) |
| `cap5_steel` | EAF loads, Port Talbot and Scunthorpe; hydrogen-DRI optional |
| `cap5_fes_ceiling`, `cap2_fes_ceiling` | onshore wind and solar held to FES 2035 (planning stand-in) |
| `cap5_fes_ceiling_import_100` | the ceiling with imports at 100 GBP/MWh as well |
| `cap5_offwind_capex64`, `cap5_offwind_capex51` | offshore capex 15 percent short of and past its cap5 breakeven |
| `cap5_wy2010` to `cap5_wy2024` | `cap5` on each weather year, 2010 to 2024 |
| `test` | one week, CI regression |

## Resolution and solver

The full sweep runs at 3-hourly resolution with HiGHS's PDLP (first-order) solver at 1e-5
feasibility tolerance. The probe that settled this was run during the build and its timings
live in the build log, not in a committed file. On a four-week slice, simplex took about 20
minutes to reach optimal; scaled to a full year it did not finish within hours. Interior
point without crossover was faster on those four weeks, about three minutes, but ended at
status "unknown" rather than "optimal", since skipping crossover leaves infeasibility above
HiGHS's threshold. PDLP solved a 3-hourly year at "optimal", in about 9 minutes on the probe
and 4 to 84 minutes across the published scenarios (`solve_seconds` in each
`results/<scenario>/run_meta.json`).

HiGHS carries two PDLP implementations and the results use both. The published sweep was
solved with cuPDLP-C (`solver: pdlp`, the default in `config/settings.yaml`) at commit
`7728e99`, except `cap5_ee_demand`, solved at `d43f866` with HiGHS's own PDLP (`solver:
hipdlp`, a per-scenario override in `config/scenarios.yaml`) after cuPDLP-C ended at status
"unknown" on it three times; the two commits differ in nothing the LP sees but that solver
choice. The robustness runs came later, each at the commit its `run_meta.json` records. Of
their full-year solves one ended at "unknown" on cuPDLP-C, `cap5_wy2010` after 31 minutes, and
was re-solved with `hipdlp`; the slowest that converged, `cap5_wy2015`, took 102 minutes.
`tests/results/` checks every run's recorded solver against config.

One scenario is still missing. `cap0p5`, the 0.5 MtCO2 cap, has not converged on either PDLP:
cuPDLP-C crawled for 1 hour 50 minutes and was killed, and HiGHS's own PDLP stopped at a
four-hour limit (status `time_limit`). That cap leaves only about 0.4 Mt for unabated gas once
blue hydrogen's 0.1 Mt is paid for, which puts the LP on the near-vertical part of the
abatement curve, exactly where a first-order method crawls. Interior point with crossover,
which ends at an exact vertex, is configured for the next attempt. The sweep therefore reports
30 down to 2 MtCO2, and `cap2` is the tightest converged cap.

PDLP satisfies constraints only to within tolerance, not at an exact vertex, so its duals
are less precise than a simplex solution's, including the shadow carbon price, and cost
differences below about 0.1 m GBP/yr on a 15.5 bn base are inside that tolerance. The
one-week harness uses simplex instead: PDLP's status was not reproducible across platforms at
this horizon, optimal on macOS, unknown on Linux CI. An hourly `cap5` run checks what
3-hourly resolution costs in accuracy: 0.4 percent on total cost, nothing on the shadow
carbon price, and about 1 GW shifted between new onshore wind and new solar.

## Provenance

Every run writes `run_meta.json`: the commit, the PyPSA and HiGHS versions, the solver, the
resolution, the weather year, the solve time and `input_fingerprint`, a hash of the unsolved
network (every component table and time series at ten significant figures, names and
descriptions left out). `tests/results/` rebuilds each committed scenario and compares
fingerprints, so a change to data, config or model code that would move a published number
fails CI until that scenario is re-solved. The same suite checks each run's energy balance
against the demand it was given, its CO2 against its cap, that its cost rows add up, and
that the README's generated table is the one the results produce;
`tests/results/test_readme_claims.py` recomputes the README's headline numbers from the
committed files and finds each one in the text.

The fingerprint covers what each network is built from, not how it was solved, so
`tests/results/` also checks the solver every run records against the one config now names
for it, and its PyPSA and HiGHS against `uv.lock`. Two kinds of provenance are recorded after
the fact, and say so: the 12 runs solved before fingerprints existed had theirs added by
rebuilding each network at its own solve commit (all 12 matched the current code), and where
`gb2035 extract` has rewritten a run's tables from its saved network, `extract_meta.json` names
the commit that did it. Re-extraction reproduced every pre-existing table byte for byte and
added `breakeven.csv`.

When the fingerprint test fails, the change has moved what that scenario builds: re-solve it
(`gb2035 run --scenario <name> --resolution-hours 3`, adding `--results-dir
results_weather_years` for the `cap5_wy` family), run `gb2035 report --update-readme`, and
commit the new tables with the change that caused them.

## Known simplifications

- No BECCS: keeps carbon accounting free of negative emissions.
- No unit commitment or reserves: dispatch is a continuous LP, not mixed-integer.
- Interconnector trade is price-taking, unbounded up to capacity at a fixed price each way.
- The interconnectors and the built grid carry no fixed cost, a small constant
  understatement of cost. Every other sunk asset, nuclear and pumped hydro included, pays
  fixed O&M.
- The GB cutout stops at longitude 1.75 east, so all three offshore lease areas are clipped
  to the part it covers: 80.5 percent of Dogger Bank's polygon area, 32.8 percent of
  Hornsea's and 87.2 percent of East Anglia's fall outside it (the warnings `gb2035
  build-profiles` prints). Their profiles come from the covered western cells.
- Offshore profiles carry no wake losses: atlite applies the 15 MW reference turbine's power
  curve to ERA5 wind with no array effects, which gives Dogger Bank a 2019 mean capacity
  factor of 0.62. PyPSA-Eur's default configuration scales offshore profiles by 0.8855 as a
  wake proxy; applying one here would make offshore dearer, not cheaper.
- The 2035 demand shape is the weather year's own, rescaled. Electrified heat and transport
  would make 2035 demand more winter-peaking than any historic year, which favours wind over
  solar; the model does not reshape for it, so its solar build is if anything flattered.
- ERA5 overstates onshore capacity factors at a few small, coastal or island zones
  (Shetland, the Western Isles, Argyll).
- Zonal demand is split by the author's own population estimates, not an official
  GSP-level breakdown.
- The headline sweep runs 3-hourly, a subsample rather than an average, not hourly as
  designed.
- The tightest cap in the design, 0.5 MtCO2, is not in the results: PDLP did not converge on
  it within the run budget.
