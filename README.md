# gb-2035-pypsa

Least-cost GB power system in 2035 under tightening carbon caps, with a Teesside industrial
hydrogen node. PyPSA + HiGHS, 20 transmission zones, hourly, weather year 2019.

## Run it

```bash
uv sync --all-extras --group dev
uv run gb2035 run --scenario test      # one week, solves in under a minute, no downloads needed
uv run gb2035 run --scenario cap5      # full year, 5 MtCO2 cap
uv run gb2035 report                   # results/summary.csv
```

Derived inputs are committed, so a fresh clone solves offline. `uv run gb2035 retrieve` fetches
the pinned raw sources (checksums in `data/manifest.json`) if you want to rebuild them with
`uv run gb2035 build-derived`; regenerating the wind and solar profiles needs the 765 MB ERA5
cutout and the `profiles` extra.

Findings, method and limitations follow once the full scenario set has run.
