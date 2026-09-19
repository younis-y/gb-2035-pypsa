# gb-2035-pypsa: design specification

Date: 2026-09-18. Status: approved in brainstorming; parameter table finalised before commit.
Repository: github.com/younis-y/gb-2035-pypsa (public). Package: `gb2035`. Licence: MIT.

## 1. Purpose and audience

A portfolio-grade energy-systems model built to the standard Systemiq's Analytiq team
expects from an Energy Associate: PyPSA plus HiGHS, tested, continuously integrated,
containerised, reproducible from a fresh clone, with a small web app and a findings-led
write-up. The primary reader is a recruiter or interviewer with energy-modelling
literacy who will spend ten minutes on the README and, if interested, run the model.

The project must also be true to its own claims. Every number in the README traces to a
committed results file, and every assumption carries a source URL.

## 2. Research question and headline outputs

**Question.** What is the least-cost GB power system in 2035 as the annual CO2 cap
tightens from roughly today's emissions to near zero; how does the optimised mix compare
with NESO's FES 2025 Holistic Transition; and what does an industrial hydrogen demand at
Teesside do to the answer?

**Headline outputs**, each a chart plus a table in `results/`:

1. Capacity mix (GW) and annual generation (TWh) by technology against the CO2 cap.
2. Total annualised system cost (GBP bn/yr) and the shadow carbon price (GBP/tCO2) from
   the cap constraint's dual, against the cap. This is the marginal abatement cost curve.
3. Optimised 2035 mix versus FES 2025 Holistic Transition capacities, side by side.
4. Storage build: battery GW/GWh, hydrogen storage GWh, hydrogen turbine GW, against the cap.
5. Teesside coupling: electrolysis capacity and utilisation, hydrogen store cycling,
   green versus blue hydrogen share, and the system-cost delta of removing the node.
6. Zonal picture on a map: installed capacity, curtailment, and inter-zone flows, with
   the Scotland to England boundary flow compared against the ETYS 2035 B6 capability.

## 3. Scope

**In scope.** One target year (2035), one weather year (2019), hourly resolution, GB
transmission zones, capacity expansion and dispatch as a single linear program, a CO2 cap
sweep, one hydrogen cluster node, a Streamlit results app with a map, Snakemake and CLI
workflows, Docker, CI, README and docs.

**Out of scope.** Multi-year pathways, unit commitment, AC power flow, reserve and
inertia products, distribution networks, demand-side response beyond electrolysis and
storage, biomass and BECCS (excluded to keep the carbon accounting free of negative
emissions), Northern Ireland, and endogenous interconnector expansion. Each exclusion is
stated in the README's "What this model does not claim" section.

## 4. Model formulation

Framework: PyPSA >= 1.3 with linopy >= 0.9 and HiGHS via highspy. Everything below is a
standard PyPSA component so the formulation is inspectable through PyPSA's own API.

### 4.1 Spatial structure

- **20 AC buses** from the PyPSA-GB zonal network (MIT): Z1_1 Shetland, Z1_2 Western
  Isles, Z1_3 North Highlands, Z1_4 West Highlands, Z2 North East Scotland, Z3 Central
  Highlands, Z4 Argyll, Z5 Central Scotland, Z6 South Scotland, Z7 North England, Z8
  Yorkshire and Humber, Z9 North West England and North Wales, Z10 Lincolnshire and East
  Midlands, Z11 Midlands, Z12 East Anglia and Central, Z13 South Wales and Severn, Z14
  London, Z15 South East, Z16 South Central, Z17 South West peninsula. Coordinates and
  polygons come from `buses.csv` and `zones.geojson`.
- **31 inter-zone links** from `links.csv` as a transport model: `Link` components with
  `p_min_pu = -1`, `p_nom` fixed at the file's capacity, no losses. In the
  `tx_expansion` scenario the links become extendable with `p_nom_min` at today's value
  and a capital cost per MW derived from HVDC/HVAC cost per MW-km in technology-data and
  the link distance in `transmission_grid_2030.yaml`.
- **Three offshore wind zones** (DOGGER_BANK, HORNSEA, EAST_ANGLIA polygons) supply
  capacity-factor series for offshore generators placed at their landing buses: Dogger
  Bank and Hornsea at Z8, East Anglia at Z12. Other zones with coastline keep a generic
  offshore generator using the nearest offshore polygon's profile, or none where FES
  places no offshore wind.
- **Interconnectors** are `Generator` components at their landing buses with
  `p_min_pu = -1` (negative dispatch is export), `p_nom` from `links_future.csv` and the
  NESO interconnector register, scaled so the total equals the FES 2035 Holistic
  Transition figure of 19.4 GW, and a flat per-country marginal price. Imports carry zero
  territorial emissions. Both simplifications are documented.
- **One hydrogen bus**, `Teesside H2`, carrier `H2`, coupled to Z7.

### 4.2 Technologies

| Component | PyPSA type | Extendable | Notes |
|---|---|---|---|
| Onshore wind | Generator | yes, per zone | `p_nom_min` = REPD operational plus under construction in the zone; `p_nom_max` from a per-zone land-availability cap in config |
| Offshore wind (fixed-bottom) | Generator | yes, at landing zones | `p_nom_min` from REPD; profile from offshore polygons |
| Solar PV | Generator | yes, per zone | `p_nom_min` from REPD |
| Nuclear | Generator | no | 5.0 GW: Hinkley Point C 3.26 GW and Sizewell B 1.2 GW, each assigned to its zone by point-in-polygon from a committed-plants table; remainder retired by 2035 in line with FES |
| Existing gas (CCGT and OCGT fleet) | Generator | retirement only | `p_nom_max` = DUKES capacity by zone, capital cost = fixed O&M only, so the model may retire plant to save O&M |
| New OCGT | Generator | yes | peaking |
| Gas CCS | Generator | yes | 90 percent capture; residual emissions through carrier `co2_emissions` |
| Battery | StorageUnit | yes, per zone | `max_hours` 2, `efficiency_store` = `efficiency_dispatch` = sqrt(0.90), wear cost as marginal cost, cyclic state of charge. Parameters lifted from the author's PuLP arbitrage LP |
| Pumped hydro | StorageUnit | no | existing 2.8 GW at its zones, from DUKES |
| Electrolysis | Link Z7 -> Teesside H2 | yes | efficiency from costs table |
| Hydrogen store | Store on Teesside H2 | yes | underground salt cavern cost class; `e_cyclic` |
| Hydrogen turbine | Link Teesside H2 -> Z7 | yes | H2 CCGT efficiency from costs table |
| Blue hydrogen | Generator on Teesside H2 | yes (scenario toggle) | marginal cost = blue LCOH; residual emissions via carrier |
| Industrial hydrogen demand | Load on Teesside H2 | n/a | flat hourly profile; annual TWh in config |
| Zonal electricity demand | Load per bus | n/a | hourly series, section 6 |

### 4.3 Time

- 8,760 hourly snapshots for 2035 using weather year 2019 for wind, solar and the demand
  shape. Snapshot weightings are 1.
- The test scenario uses one week, 2019-01-14 to 2019-01-20 inclusive (168 snapshots),
  chosen as a high-demand winter week, with snapshot weightings scaled so annual
  quantities remain comparable in magnitude.
- An optional `resolution_hours: 3` setting resamples to 2,920 snapshots with weight 3
  for quick iteration. Headline results always run hourly.

### 4.4 Carbon

A `GlobalConstraint` of type `primary_energy` on the `co2_emissions` carrier attribute
limits annual emissions from gas, gas CCS and blue hydrogen. Its dual is written to
results as the shadow carbon price. The `uncapped` scenario has no constraint and adds
the UK ETS price to marginal costs instead.

### 4.5 Objective

Minimise annualised capital cost plus fixed O&M plus variable O&M plus fuel plus carbon
price (uncapped run only). Capital cost per MW-year = capex x annuity(discount rate,
lifetime) + fixed O&M. One system-wide discount rate in config, default 0.07, with
per-technology override permitted through the costs table.

## 5. Scenarios

Defined in `config/scenarios.yaml`; each scenario is a diff against `config/settings.yaml`.

| Scenario | Purpose |
|---|---|
| `uncapped` | Reference with UK ETS carbon price, no cap |
| `cap30`, `cap20`, `cap10`, `cap5`, `cap2`, `cap0p5` | CO2 cap sweep, MtCO2/yr |
| `cap5_no_h2` | `cap5` with Teesside demand set to zero, isolates the coupling effect |
| `cap5_ee_demand` | `cap5` with Electric Engagement demand totals |
| `cap5_tx_expansion` | `cap5` with extendable inter-zone links |
| `cap5_steel` (stretch) | `cap5` plus EAF electricity loads at Port Talbot (Z13) and Scunthorpe (Z8) and an optional hydrogen-DRI hydrogen demand, technologies named as in Steel-IQ (`DRI-H2`, `EAF`) |
| `test` | one-week, all technologies, used by CI with an expected objective |

## 6. Data sources and retrieval

All external files are declared in `data/manifest.json` with URL, pinned commit or tag
where the host allows it, SHA-256, size and licence. `gb2035 retrieve` downloads to
`data/raw/` (git-ignored) and verifies checksums. Small derived tables are committed under
`data/derived/` so a fresh clone builds and solves offline.

| Input | Source and licence | Derived artefact (committed) |
|---|---|---|
| Zones, buses, links, interconnectors, zone polygons, 2030 link capacities | PyPSA-GB `data/network/zonal/*` at a pinned commit, MIT; topology originally UK-Calliope | copied as-is (about 280 KB) |
| Thermal, nuclear and hydro fleet | PyPSA-GB `data/generators/dukes_power_station_coordinates.csv` (DUKES 5.11 2025, 1,369 plants, EPSG:27700), MIT | `fleet_by_zone.csv`: zone x technology MW after point-in-polygon |
| Renewables floor | DESNZ REPD Q2 2026 CSV, OGL v3; columns Technology Type, Installed Capacity (MWelec), Development Status (short), X-coordinate, Y-coordinate | `repd_by_zone.csv`: zone x technology MW for Operational and Under Construction |
| Demand shape | NESO Historic Demand Data 2019 CSV, NESO Open Data Licence; gross underlying demand = ND + EMBEDDED_WIND_GENERATION + EMBEDDED_SOLAR_GENERATION, half-hourly averaged to hourly | `demand_2019_hourly.parquet` (national, 8,760 rows) |
| Zonal demand split | author population estimates per zone in `config/demand_weights.csv` (the PyPSA-GB `zone_definitions.csv` covers only 37 GSPs and leaves Z1_1, Z1_2, Z1_3, Z4 and Z10 without weight); FES 2025 GSP building blocks remain the stretch upgrade | `demand_weights.csv` |
| 2035 totals | FES 2025 Data Workbook V006 sheets F.53 to F.64, DB.ED1, F.24 to F.26 | `fes2025_gb_2035.csv`: metric, pathway, value, unit, sheet |
| Wind and solar profiles | Zenodo record 18325225 `uk-2019.nc` ERA5 cutout (765 MB, CC-BY 4.0) processed once with atlite over `zones.geojson` including the three offshore polygons | `cf_2019_zonal.parquet`: 8,760 x (zone, carrier), about 1 MB |
| Technology costs | PyPSA technology-data `outputs/costs_2035.csv` at tag v0.15.0 (EUR 2025), converted to GBP at one documented rate; DESNZ Electricity Generation Costs 2025 Annex A (GBP 2024) overrides for solar, onshore, offshore, CCGT, OCGT, gas CCS, hydrogen to power | `costs_2035_gb.csv`: technology, parameter, value, unit, source |
| Fuel and carbon prices | DESNZ fossil fuel price assumptions (central, 2035) and UK ETS | in `assumptions.yaml` with URLs |
| Hydrogen, steel and carbon-budget parameters | see section 7 | in `assumptions.yaml` with URLs |

Renewables.ninja is not used in the pipeline because its GB country files are CC BY-NC; it
may be cited as a validation cross-check in docs only.

## 7. Assumptions and parameters

Values the code ships with. Each has a `source` URL and a `confidence` tag in
`config/assumptions.yaml` (`published` = read from the cited document; `derived` = arithmetic
on published figures, shown; `assumption` = author's choice, with reasoning). Technology
capex, fixed and variable O&M, efficiencies and lifetimes are not listed here: they are
generated into `data/derived/costs_2035_gb.csv` with a source per row (technology-data
v0.15.0 with DESNZ Electricity Generation Costs 2025 Annex A medium values overriding solar,
onshore wind, fixed offshore wind, CCGT, OCGT, gas CCS and hydrogen to power).

| Parameter | Value | Unit | Confidence, source |
|---|---|---|---|
| Target year, weather year | 2035, 2019 | | assumption: 2019 is a non-COVID year with a Zenodo cutout |
| Annual zonal load, Holistic Transition | 388.3 x 1.07 = 415.5 | TWh | derived: FES 2025 F.53 consumer demand x transmission-and-distribution losses uplift; the uplift reconciles to FES DB.ED1 system demand net of electrolysis |
| Annual zonal load, Electric Engagement | 407.8 x 1.07 = 436.3 | TWh | derived, same method |
| Zonal demand split | population weights by zone | share | published: author population estimates per zone in `config/demand_weights.csv` (the PyPSA-GB `zone_definitions.csv` covers only 37 GSPs and leaves Z1_1, Z1_2, Z1_3, Z4 and Z10 without weight); FES 2025 GSP building blocks remain the stretch upgrade |
| Nuclear fleet 2035 | 5.0 (Hinkley Point C 3.26 at 51.209N 3.130W; Sizewell B 1.20 at 52.215N 1.620E) | GW | published: FES 2025 F.62 total; plant data EDF |
| Interconnector capacity 2035 | 19.4, split by landing zone pro rata to `links_future.csv` | GW | published: FES 2025 F.61 (HT) |
| Interconnector price, both directions | 65 | GBP/MWh | assumption: rounded 2024 GB day-ahead annual mean; single flat price, sensitivity in docs |
| Gas price 2035 | 24 | GBP/MWh thermal | published: DESNZ fossil fuel price assumptions, central case, converted from p/therm |
| Gas emission factor | 0.184 | tCO2/MWh thermal | published: DESNZ GHG conversion factors, natural gas gross CV |
| Existing CCGT efficiency | 0.50 | | assumption: fleet average |
| Gas CCS capture rate | 0.90 | | published: technology-data |
| Electrolysis efficiency (LHV) | 0.67 | | published: technology-data 2035 |
| Hydrogen turbine efficiency | 0.50 | | published: PyPSA-GB hydrogen rule |
| Battery duration, round-trip efficiency, wear cost | 2 h, 0.90 (0.9487 each way), 0.09 GBP/MWh | | published: author's PuLP LP (0.1 EUR/MWh wear converted) |
| Teesside industrial hydrogen demand, HT | 19.8 x 0.25 = 5.0 | TWh/yr | derived: FES 2025 F.51 industrial demand x Teesside share; TVCA states 2.5 GW of the UK's 10 GW 2030 ambition |
| Teesside industrial hydrogen demand, EE | 5.1 x 0.25 = 1.3 | TWh/yr | derived, same method |
| Committed Teesside electrolysis | 0 | MW | published: bp cancelled HyGreen Teesside, 4 March 2025 |
| Blue hydrogen option | up to 1.2 GW H2 output, marginal cost 70 GBP/MWh H2, residual 0.02 tCO2/MWh H2 | | published capacity (bp H2Teesside); cost and residual are assumptions from DESNZ hydrogen production cost ranges and 95 percent capture |
| CO2 cap sweep | 30, 20, 10, 5, 2, 0.5 | MtCO2/yr | anchored on DESNZ provisional 2024 electricity supply emissions of 37.5 MtCO2e |
| UK ETS price (uncapped run) | 55 | GBP/tCO2 | published: mid-2025 market level; Carbon Price Support is 0 in 2035 (abolished April 2028) |
| Discount rate | 0.07 | | assumption: common PyPSA practice; per-technology override allowed |
| EUR to GBP | 0.85 | | published: 2025 average reference rate |
| Onshore wind cap | 60 national, split by zone land area, never below the REPD floor | GW | assumption informed by FES 2035 onshore 38.4 GW and `uk-onshore-wind-siting` |
| Solar cap | 150 national, split by zone land area | GW | assumption informed by FES 2035 solar 61.8 GW |
| Offshore wind cap | 150 national: 60 percent at Z8, 25 percent at Z12, 15 percent spread over other coastal zones | GW | assumption informed by the Crown Estate leasing pipeline and FES 2035 offshore 86.1 GW |
| Steel scenario, Port Talbot EAF | 3.0 Mt/yr x 0.5 MWh/t = 1.5 TWh/yr at Z13 | | published capacity (Tata Steel); intensity derived |
| Steel scenario, Scunthorpe EAF | 3.0 Mt/yr x 0.5 MWh/t = 1.5 TWh/yr at Z8 | | assumption: capacity of the consented EAF plan is not confirmed |
| Steel scenario, hydrogen DRI sensitivity | 51 kg H2/t and 0.7 MWh/t electricity excluding electrolysis, applied to Port Talbot | | published: Vogl et al. 2018 (3.48 MWh/t including electrolysis) |

## 8. Architecture

Source layout follows steel-iq's separation of domain, adapters and entrypoints without
its message-bus machinery.

```
src/gb2035/
  config.py          pydantic models: Settings, Scenario, Assumptions; YAML loaders; validation
  cli.py             typer app: retrieve, build-profiles, build-network, solve, report, run
  data/
    manifest.py      read manifest.json, verify SHA-256
    retrieve.py      download with resume and checksum verification
    zones.py         load zones.geojson, point-in-polygon assignment (EPSG:27700 and 4326)
    fleet.py         DUKES plants -> fleet_by_zone.csv
    repd.py          REPD -> repd_by_zone.csv
    demand.py        NESO historic demand -> hourly gross demand; zonal split; FES scaling
    profiles.py      atlite cutout -> zonal capacity factors (optional dependency `profiles`)
    costs.py         technology-data + DESNZ overrides -> costs_2035_gb.csv; annuity helper
    fes.py           FES 2025 workbook -> fes2025_gb_2035.csv
  model/
    network.py       build_network(scenario, inputs) -> pypsa.Network
    components.py    add_generators, add_storage, add_hydrogen_cluster, add_interconnectors, add_links
    constraints.py   add_co2_cap, add_steel_loads
    solve.py         solve(network, solver options) -> status; writes network .nc
  results/
    extract.py       capacities, energy, emissions, costs, duals, flows, curtailment, hydrogen -> CSV/parquet
    summary.py       cross-scenario summary.csv and README tables
  report/
    figures.py       dataviz-skill charts for README and app
app/
  streamlit_app.py, pages/
workflow/Snakefile
config/{settings.yaml, scenarios.yaml, assumptions.yaml}
data/{manifest.json, raw/ (ignored), derived/}
results/{scenario}/, results/summary.csv
tests/{unit, integration, architecture, e2e, fixtures}
docs/{methodology.md, data_sources.md, assumptions.md, steel_iq_link.md, superpowers/}
```

**Data flow.** `retrieve` -> `data/raw` -> per-source builders -> `data/derived` ->
`build_network(scenario)` -> `solve` -> `results/{scenario}/network.nc` -> `extract` ->
CSV/parquet -> `summary` and `figures` -> README tables and the Streamlit app.

**Interfaces.** Every builder is a pure function from typed inputs to a DataFrame or
Network; no module reads environment variables or global state. Parameters flow only
through `Settings`, `Scenario` and `Assumptions` objects. An architecture test enforces
this by scanning `src/gb2035/{data,model,results}` for imports of `os.environ`, `dotenv`
or `gb2035.config.load_*`.

**Error handling.** Missing raw files raise a `RetrieveError` naming the manifest entry
and the CLI command that fetches it. Checksum mismatches fail loudly. A solve that is not
optimal raises `SolveError` with solver status and condition; results are never written
for a non-optimal solve. Point-in-polygon assignment logs the share of MW that fell
outside every polygon and fails if it exceeds 2 percent.

## 9. Configuration

`config/settings.yaml` holds model-wide defaults: weather year, resolution, discount
rate, currency conversion, solver options, paths. `config/scenarios.yaml` holds named
diffs: cap, demand pathway, Teesside demand, blue hydrogen toggle, transmission
expansion, steel loads. `config/assumptions.yaml` holds every sourced number with
`value`, `unit`, `source` and `note`. Pydantic validates types, ranges and cross-field
rules (for example a cap scenario cannot also set a carbon price). `gb2035 config show
--scenario cap5` prints the merged, validated configuration.

## 10. CLI and workflow

- `gb2035 retrieve [--only name]`
- `gb2035 build-derived` (fleet, repd, demand, costs, fes)
- `gb2035 build-profiles --cutout data/raw/uk-2019.nc` (needs the `profiles` extra)
- `gb2035 build-network --scenario cap5`
- `gb2035 solve --scenario cap5`
- `gb2035 extract --scenario cap5`
- `gb2035 report` (summary plus figures across all solved scenarios)
- `gb2035 run --scenario cap5` runs build, solve and extract.

`workflow/Snakefile` wraps these with a `{scenario}` wildcard so `snakemake --cores 4
results/summary.csv` reproduces everything; CI runs `snakemake -n` and a real run of the
`test` scenario. Snakemake is a dev extra, not a runtime dependency.

## 11. Results store

Per scenario under `results/{scenario}/`: `network.nc` (git-ignored), `capacities.csv`,
`energy.csv`, `emissions.csv`, `costs.csv`, `duals.csv`, `flows.csv`, `curtailment.csv`,
`hydrogen.csv`, `dispatch_hourly.parquet`. Across scenarios: `results/summary.csv`. The
CSVs for the headline scenarios are committed; parquet and netCDF are not.

## 12. Streamlit app

Read-only over `results/` and `data/derived/zones.geojson`, so it starts in seconds and
can be deployed to Streamlit Community Cloud from the public repo. Pages: Overview
(cost and shadow-price curves, capacity mix), Map (folium choropleth of capacity or
curtailment by zone, link flows as weighted lines, Teesside marker), Dispatch (week
picker, stacked area by carrier, zonal price), Hydrogen (electrolysis utilisation, store
level, green versus blue), Assumptions (costs and sources table). Charts follow the
dataviz skill's palette and mark rules.

## 13. Testing

- **Unit** (`tests/unit`, offline, fixtures under `tests/fixtures`): config validation
  and merging; annuity arithmetic; point-in-polygon assignment with known coordinates
  (Teesside -> Z7, Scunthorpe -> Z8, Port Talbot -> Z13); demand gross-up and scaling;
  capacity-factor aggregation bounds in [0, 1]; costs override precedence; network
  build invariants (bus count 21, link count, every load has a bus, every generator has a
  carrier, `p_nom_min <= p_nom_max`); carbon constraint present only in cap scenarios.
- **Integration** (`tests/integration`, marked `slow`): build and solve the `test`
  scenario; assert optimal status, energy balance closes per bus within tolerance, cap
  binds when tight and dual is positive, objective within 0.5 percent of a committed
  expected value; PyPSA `StorageUnit` reproduces the PuLP battery LP's daily profit on a
  fixture day of prices to within 1 percent (same physics, different solver).
- **Architecture** (`tests/architecture`): no global state imports in core modules;
  every assumption in `assumptions.yaml` has a non-empty `source`.
- **End to end** (`tests/e2e`): CLI `run --scenario test` into a temporary results
  directory produces every expected file.
- Markers: `slow`, `network` (deselected by default). Target: unit suite under 30 s.

## 14. CI, Docker, repo hygiene

- `.github/workflows/ci.yml` on push and pull request: uv sync, ruff check and format
  check, mypy, pytest (unit and integration), `snakemake -n`. Python 3.13.
- `.github/workflows/docker.yml`: build the image and run `gb2035 run --scenario test`
  inside it; push to GHCR on main.
- `Dockerfile`: `python:3.13-slim`, uv, non-root user, `ENTRYPOINT ["gb2035"]`, volumes
  for `data/raw` and `results`.
- pre-commit: ruff (lint and format) and gitleaks. `justfile` with `test`, `lint`,
  `typecheck`, `run`, `app`, `docs`.
- README badges: CI, Docker, licence, Python version.

## 15. Reuse of prior work

- Battery physics and wear cost from `gb-weather-to-price-forecasting` become the battery
  technology definition, and a test reproduces that repo's daily arbitrage result inside
  PyPSA.
- The REPD capacity-weighting idea from the same repo is reused to weight renewable
  generators within zones.
- `heat-pump-peak-demand-modelling` supplies an after-diversity heat pump demand of
  about 5.5 kW per home; a stretch scenario adds a temperature-driven heat pump component
  to the demand shape using FES heat pump counts.
- `uk-onshore-wind-siting` informs the per-zone onshore `p_nom_max` caps.
- The Steel-IQ link: technology naming, the frozen-config discipline, the test layout
  and the manifest-with-checksums pattern are copied from Systemiq's repo, and the steel
  scenario uses Steel-IQ's route names so the two models could share assumptions.

## 16. Delivery phases and definition of done

1. **Scaffold and solve**: repo, packaging, config, retrieve, derived tables, network
   build, `test` scenario solving, unit and integration tests, CI green, repo public.
2. **Full-year results**: profiles from the cutout, cap sweep and variant scenarios
   solved hourly, results committed, README findings written from `summary.csv`.
3. **Presentation**: Streamlit app with map, Docker, Snakemake, docs.
4. **Review**: adversarial review of claims against artefacts, fix test-first, tag v0.1.0.

Done means: `git clone && uv sync && uv run gb2035 run --scenario test` works offline;
CI and Docker workflows green; at least ten scenarios committed; README numbers all trace
to files; app runs locally; review findings closed.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| PyPSA 1.3 and pandas 3 API churn | probe already solved a capped expansion LP on this stack; pin versions in `uv.lock` |
| Full-year solve too slow | M4 Max with 36 GB; fallback `resolution_hours: 3` for iteration, hourly for headline |
| atlite on a 765 MB cutout | one-off local step, derived parquet committed; documented regeneration route |
| REPD URL changes quarterly | manifest pins the exact asset URL and checksum; retrieve fails loudly |
| FES workbook parsing brittleness | extract once into a 30-row CSV with sheet references; no runtime Excel parsing |
| Over-claiming in README | every number generated from `summary.csv` by `report`; adversarial review before release |
| Docker cannot be built locally | build and test in GitHub Actions only |
