# Data sources

## Approach

Every external input is pinned in `data/manifest.json`: URL, SHA-256 checksum, licence,
source note. `gb2035 retrieve` downloads each entry to `data/raw/` (git-ignored) and
verifies its checksum. `gb2035 build-derived` reads `data/raw/` and regenerates the tables
committed under `data/derived/`, so a fresh clone builds and solves offline. `cf_2019_zonal.parquet` is the
exception: it needs `gb2035 build-profiles`, the `profiles` extra (atlite) and the 765 MB
Zenodo cutout.

## External inputs (13 files in `data/manifest.json`)

| Manifest key | What it is | Licence | Feeds |
|---|---|---|---|
| `pypsa_gb_buses` | 20-zone bus list | PyPSA-GB, MIT | `buses.csv` |
| `pypsa_gb_links` | inter-zone links | PyPSA-GB, MIT | `links.csv` |
| `pypsa_gb_links_future` | planned links | PyPSA-GB, MIT | `links_future.csv` |
| `pypsa_gb_zone_definitions` | GSP-to-bus map, 37 GSPs | PyPSA-GB, MIT | `zone_definitions.csv` (unused for demand, see below) |
| `pypsa_gb_zones_geojson` | zone polygons, 20 land + 3 offshore | PyPSA-GB, MIT | `zones.geojson` |
| `pypsa_gb_transmission_2030` | 2030 link capacities | PyPSA-GB, MIT (UK-Calliope) | `transmission_grid_2030.yaml` |
| `pypsa_gb_power_stations` | CCGT/OCGT locations | PyPSA-GB, MIT; DUKES 5.11, OGL v3 | `fleet_by_zone.csv` |
| `repd_q2_2026` | REPD, Q2 2026 | DESNZ, OGL v3 | `repd_by_zone.csv` |
| `neso_demand_2019` | half-hourly demand | NESO Open Data Licence | `demand_2019_hourly.parquet` |
| `fes2025_workbook` | FES 2025 Data Workbook V006 | NESO Open Data Licence | `fes2025_gb_2035.csv` |
| `technology_data_costs_2035` | technology costs, v0.15.0 | GPL-3.0 code, CC-BY-4.0 data | `costs_2035_gb.csv` |
| `desnz_generation_costs_2025_annex_a` | Generation Costs 2025 Annex A | DESNZ, OGL v3 | overrides in `costs_2035_gb.csv` |
| `zenodo_cutout_uk_2019` | ERA5 cutout | Zenodo 18325225, CC-BY-4.0 | `cf_2019_zonal.parquet` |

## Derived tables

REPD gives OSGB eastings/northings (EPSG:27700). PyPSA-GB's power station list and
`committed_plants.csv` give WGS84 lat/lon (EPSG:4326). `zones.geojson` is reprojected to
EPSG:4326 for point-in-polygon tests, and to EPSG:27700 (metres) for nearest-zone distances.

### fleet_by_zone.csv (18 rows: zone, technology, MW)

From `power_stations_locations.csv` (CCGT and OCGT only) plus `config/committed_plants.csv`
(Hinkley Point C 3,260 MW and Sizewell B 1,198 MW nuclear). Each plant is placed by
point-in-polygon; a plant outside every polygon snaps to the nearest zone within 5 km
(`COASTAL_SNAP_M`), since generalisation misses are sub-kilometre (Hinkley Point C is 372 m
outside its polygon). If unassigned capacity after the snap exceeds 2
percent of the fleet, the build fails. Totals: CCGT 28,082 MW, OCGT 1,606 MW, nuclear 4,458
MW (4.46 GW), against FES Holistic Transition 2035's 5.04 GW (`config/assumptions.yaml`).
Regenerate: `gb2035 build-derived`.

### repd_by_zone.csv (115 rows: zone, technology, status, MW)

From `REPD_Publication_Q2_2026.csv`, filtered to five technologies (onshore/offshore wind,
solar, battery, pumped hydro) and two statuses, Operational and Under Construction: capacity
already built or committed, the model's floor. Northern Ireland rows are dropped;
17 MW of multi-site portfolio rows (REPD refs 1613, 1616) have no coordinates and are
dropped too, a known loss; the 17 MW was observed during the build, since only the surviving
rows reach the committed table. Onshore points use point-in-polygon on OSGB coordinates.
Offshore wind inside one of the three named offshore polygons is attributed to its landing
zone: Dogger Bank and Hornsea to Z8, East Anglia to Z12. Anything outside every polygon
falls back to the nearest land zone,
unbounded, unlike the fleet builder's 5 km cap. Totals (operational / under
construction, MW): onshore wind 14,293 / 2,012; offshore wind 16,011 / 11,845; solar
10,923 / 3,213; battery 4,946 / 9,707; pumped hydro 2,828 / 0. Regenerate:
`gb2035 build-derived`.

### demand_2019_hourly.parquet (8,760 rows, one series: `gross_demand_mw`)

From `demanddata_2019.csv`. NESO's ND excludes embedded generation, so embedded wind and
solar are added back to recover 2035 gross demand. Each half-hour is timestamped from
settlement date and period, then averaged to hourly. Clock-change days are stamped naively:
this duplicates two half-hours on 2019-10-27 and fabricates one hour on 2019-03-31, about
0.0003 percent of annual energy (measured during the build; the committed parquet holds only
the corrected hourly series), and does not propagate because the series is later rescaled to
a chosen FES demand total. Only the national series lives here;
the zonal split (`config/demand_weights.csv`) and FES-pathway scaling happen later.
Regenerate: `gb2035 build-derived`.

### fes2025_gb_2035.csv (65 rows: metric, pathway, value, unit, sheet, block)

From `fes2025_data_workbook.xlsx` for year 2035, across up to five pathways. Thirteen
metrics come from named sheets: demand and peak demand (F.53, F.54), offshore/onshore wind
(F.55, F.56), solar (F.57), battery/long-duration storage (F.59, F.60), interconnectors
(F.61), nuclear (F.62), hydrogen generation and gas CCUS (F.63, blocks 0 and 1), unabated
gas (F.64), industrial hydrogen (F.51). Regenerate: `gb2035 build-derived`.

### costs_2035_gb.csv (16 rows, indexed by technology)

Twelve technologies come from `costs_2035.csv`, converted EUR to GBP at 0.85
(`config/assumptions.yaml`, ECB 2025 annual average). Four more (`ccgt_existing`,
`gas_ccs`, `h2_ccgt`, `pumped_hydro`) come entirely from overrides.
`config/costs_overrides.csv` applies DESNZ Generation Costs 2025 Annex A, 2035 medium
scenario, to eight of the sixteen technologies: DESNZ capex is predevelopment plus
construction cost, and DESNZ fixed O&M folds in insurance and grid connection.
`ccgt_existing` keeps zero (sunk) capex but the DESNZ CCGT fixed cost, so retirement saves
it. `pumped_hydro` is the ninth overridden technology and the one DESNZ does not cover: it
carries zero capex (the fleet is built) and an author-assumption 40,000 GBP/MW/yr fixed O&M,
so the sunk pumped-storage fleet is costed like every other brownfield asset.
Regenerate: `gb2035 build-derived`.

### cf_2019_zonal.parquet (8,760 rows x 63 columns)

Built once with atlite over `uk-2019.nc` and `zones.geojson`: onshore wind (turbine
Vestas_V112_3MW) and solar (panel CSi) for the 20 land zones, offshore
wind (turbine NREL_ReferenceTurbine_2020ATB_15MW_offshore) for the three named offshore
polygons, plus a generic offshore column per land zone (their mean). Every shape is clipped
to the cutout's bounds before atlite runs, buffering outward in 0.25-degree steps if needed,
because the cutout ends at longitude 1.75 while the East Anglia polygon reaches about
longitude 3.15, both observed during the build (the 765 MB cutout is not committed). East
Anglia's clipped profile comes from the nearest covered cells west of the site, a documented
bias. Onshore figures above 0.50, Shetland 0.615, Western Isles 0.518, Argyll 0.537, come
from ERA5's roughly 25 km cells blending marine boundary-layer wind into small island zones, so the
plausibility band tested was widened to 0.15-0.65 onshore (0.35-0.65
offshore, 0.08-0.14 solar). Regenerate: `gb2035 build-profiles --cutout data/raw/uk-2019.nc`
(`profiles` extra).

### The six copied PyPSA-GB zonal files

`buses.csv` (20 rows), `links.csv` (37), `links_future.csv` (14), `zone_definitions.csv`
(37), `zones.geojson` (23 polygons: 20 land, 3 offshore) and `transmission_grid_2030.yaml`
are copied byte-for-byte by `build-derived`, untransformed; only `zones.geojson` is loaded
by model code (reprojected as above). `zone_definitions.csv` is not used
for the demand split; see below. Regenerate: `gb2035 build-derived`.

## Zonal demand weights, renewable caps and CCS siting

`config/demand_weights.csv` holds one population-share weight per land zone (20 rows),
each an author estimate from ONS mid-2022 population, normalised to sum to 1. It exists
because PyPSA-GB's own `zone_definitions.csv` resolves only 37 GSPs and leaves five land
zones (Z1_1, Z1_2, Z1_3, Z4, Z10) with no weight.

`config/renewable_caps.yaml` sets national greenfield caps of 60 GW onshore, 150 GW solar,
150 GW offshore (`config/assumptions.yaml`, informed by FES 2025 sheets F.56, F.57, F.55),
on top of the REPD operational-plus-under-construction floor: existing capacity is added
back separately as a fixed unit, never counted against the cap.
Onshore and solar caps split by land area; offshore splits by named share: Dogger Bank 35
percent, Hornsea 25 percent, East Anglia 25 percent, the remaining 15 percent spread across
six generic coastal zones (Z2, Z7, Z13, Z15, Z16, Z17).

`config/ccs_zones.yaml` lists the six zones a gas CCS plant may be built in: Z7 Teesside and
Z8 Humber (East Coast Cluster), Z9 Merseyside and North Wales (HyNet), Z5 Grangemouth
(Acorn), and Z13 South Wales and Z16 Solent as Track-2 candidates. It is an author assumption
informed by the DESNZ CCUS cluster sequencing, sourced as `ccs_hosting_zones` in
`config/assumptions.yaml`. Without it the optimiser sites CCS in every zone, islands
included, because nothing in a transport-model LP knows a CO2 pipeline has to reach the site.

## Licences

| Licence | Covers |
|---|---|
| MIT | PyPSA-GB zonal files and power station locations |
| OGL v3 | REPD and DESNZ Generation Costs 2025 Annex A |
| NESO Open Data Licence | the 2019 demand history and FES 2025 Data Workbook |
| CC-BY-4.0 | the Zenodo ERA5 cutout, and technology-data's data (code is GPL-3.0) |

Renewables.ninja was not used: its GB files are CC BY-NC licensed.
