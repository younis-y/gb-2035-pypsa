# Steel-IQ link

gb2035 is a power-system model; Systemiq's Steel-IQ is a steel-plant model. They share no
code or data today. gb2035's engineering follows several of Steel-IQ's conventions, at a
much smaller scale, and one scenario borrows its vocabulary for a UK steel-electrification
sensitivity.

## What was adopted

Both repos use `uv` for dependency management with `hatchling` as the build backend, and
both target Python 3.13. gb2035 runs `ruff` (lint and format) as a pre-commit hook the way
Steel-IQ does, though gb2035 adds a `gitleaks` secret scan alongside it, which Steel-IQ does
not have. Both use `mypy` in strict mode with the `pydantic.mypy` plugin. gb2035's test
suite mirrors Steel-IQ's tiering, `tests/{unit, integration, e2e, architecture}`, a narrower
set than Steel-IQ's own, which also splits out its web and simulation layers. Both include
an architecture test that fails if core model code imports global configuration directly
(`os.environ`, `dotenv` or the config loader in gb2035; `steelo.config` in Steel-IQ), so
every parameter has to arrive through an explicit settings object instead. Neither repo
commits its raw external data: gb2035's `data/manifest.json` records each source's URL,
checksum and licence, and a `retrieve` command downloads and verifies it, the same shape as
Steel-IQ's own manifest-backed data store. Configuration in gb2035 is frozen throughout,
`Settings`, `Scenario`, `HydrogenSettings`, `SteelSettings` and `Assumption` are all
immutable pydantic models. Steel-IQ's own top-level `SimulationConfig` is a plain, mutable
dataclass, but its per-technology settings are themselves frozen dataclasses; gb2035
generalises that same immutability everywhere, using pydantic instead.

## What was left out

Steel-IQ's real source of truth is a master Excel workbook, tens of megabytes, parsed into
JSON on first use. gb2035 has no equivalent: every input is a small, sourced CSV or parquet
file, and `config/assumptions.yaml` holds every number by hand with a source URL and a
confidence tag. Steel-IQ's domain logic also lives mostly in one large module. gb2035 splits
the model build into four short files instead (`components.py`, `constraints.py`,
`network.py`, `solve.py`), each responsible for one part of the network.

## The cap5_steel scenario

Steel-IQ names three primary steelmaking routes: `DRI`, `DRIH2` and `EAF`. `cap5_steel`
borrows two of them.

`cap5_steel` adds two electricity loads on top of `cap5`: an electric-arc-furnace load at
Port Talbot (Z13) and one at Scunthorpe (Z8), each 1.5 TWh/yr (3 Mt/yr of steel at 0.5
MWh/t; Port Talbot's is Tata Steel's published figure, Scunthorpe's mirrors it as an
assumption, since its consented EAF plant's capacity is unconfirmed). The loads are named
`eaf Port Talbot` and `eaf Scunthorpe`, echoing Steel-IQ's `EAF` route code.

The scenario also carries an optional hydrogen-DRI block, off by default and in the
committed sweep (`h2_dri_enabled: false`), sized for 3 Mt/yr of steel at Port Talbot: 51 kg
of hydrogen per tonne and 0.7 MWh of electricity per tonne excluding electrolysis, both from
Vogl, Ahman and Nilsson (2018), whose own total is 3.48 MWh/t including electrolysis. All
three numbers are sourced rows in `config/assumptions.yaml`, and
`tests/unit/test_config.py::test_repo_config_files_load` asserts each against the
`SteelSettings` default that carries it, so the code and the sourced table cannot drift apart:

| `SteelSettings` field | `assumptions.yaml` key |
|---|---|
| `h2_kg_per_t` | `h2_dri_kg_per_t` |
| `dri_electricity_mwh_per_t` | `dri_electricity_mwh_per_t` |
| `h2_dri_mt_steel` | `h2_dri_mt_steel` |
| `h2_lhv_mwh_per_t` | `h2_lhv_mwh_per_t` |

The first pair is the one the names do not match on, and it was the pair the guard missed: the
51 kg/t figure went unasserted until this table was written. The same test pins
`HydrogenSettings.turbine_efficiency` to `hydrogen_turbine_efficiency` and the three numeric
`blue_h2_*` defaults to their rows. Enabled, the block
reuses the Teesside electrolysis-store-turbine node with blue hydrogen off. gb2035 has no
PyPSA carrier called `DRIH2`: the borrowing is in spirit, an electrolytic, green-only route
feeding steelmaking, rather than in exact naming.

In the committed sweep the two EAF loads add 180 m GBP/yr to the 5 MtCO2 system, 15.0 bn
against `cap5`'s 14.8 bn (`results/summary.csv`), which over 3.0 TWh is 60 GBP/MWh, close to
the 61 GBP/MWh zonal electricity price the model already clears at
(`results/cap5/duals.csv`). Electrifying both plants is, on these numbers, a demand-side
change the power system absorbs by building 1.1 GW more onshore wind and 0.7 GW more solar,
not a structural one.

## A shared assumptions interface

A real link between the two models would trade two kinds of numbers. From gb2035: a
hydrogen price at the Teesside or Port Talbot bus and an electricity price by zone, both read
off the bus's marginal price, the same kind of dual value the CO2 cap already produces here.
`cap5` already publishes both, 71.0 GBP/MWh for hydrogen at Teesside and about 61 GBP/MWh for
electricity in every zone (`results/cap5/duals.csv`); a steel model could consume them as
they stand. From a steel model: electricity and hydrogen intensity per tonne for each route
it models (`DRI`, `DRIH2`, `EAF`), against which gb2035 currently carries one literature pair
for the hydrogen route and a flat 0.5 MWh/t for `EAF`. Steel-IQ does not yet publish UK plant
data or per-tonne intensities either; its own hydrogen price today is a country-level LCOH
derived from a regional electricity price and capped by a percentile rule, not read from a power-system
model. Wiring the two together, prices out of gb2035 and intensities out of a steel model,
is future work, not something either repository does now.
