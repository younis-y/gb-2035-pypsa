"""Command-line entry points: retrieve -> build-derived -> build-profiles -> run -> report."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Annotated, Any, cast

import pypsa
import typer
from rich.console import Console

from gb2035 import __version__
from gb2035.config import Scenario, Settings, list_scenarios, load_scenario, load_settings
from gb2035.data.costs import build_costs
from gb2035.data.demand import load_neso_demand
from gb2035.data.fes import extract_fes_2035
from gb2035.data.fleet import build_fleet_by_zone
from gb2035.data.manifest import load_manifest, save_manifest
from gb2035.data.repd import build_repd_by_zone
from gb2035.data.retrieve import retrieve
from gb2035.data.zones import load_zones
from gb2035.model.inputs import load_inputs
from gb2035.model.network import build_network
from gb2035.model.solve import SolveResult, fixed_asset_cost_gbp_per_yr, solve
from gb2035.paths import ProjectPaths
from gb2035.results.extract import extract_all, write_results
from gb2035.results.summary import write_summary

app = typer.Typer(add_completion=False, no_args_is_help=True, help="GB 2035 power-system model.")
console = Console()

RootOpt = Annotated[Path, typer.Option("--root", help="Project root (contains config/ and data/).")]
ResultsOpt = Annotated[
    Path | None,
    typer.Option("--results-dir", help="Where to write results (default <root>/results)."),
]
ScenarioOpt = Annotated[
    str, typer.Option("--scenario", help="Scenario name from config/scenarios.yaml.")
]
ResolutionHoursOpt = Annotated[
    int | None,
    typer.Option(
        "--resolution-hours",
        help="Override settings.resolution_hours (e.g. 3 for 3-hourly snapshots).",
    ),
]


def _ctx(root: Path, results_dir: Path | None) -> tuple[ProjectPaths, Settings, Path]:
    paths = ProjectPaths(root.resolve())
    settings = load_settings(paths.config / "settings.yaml")
    return paths, settings, (results_dir or paths.results).resolve()


def _with_resolution(settings: Settings, resolution_hours: int | None) -> Settings:
    """Override `settings.resolution_hours`, or return `settings` unchanged when not given."""
    if resolution_hours is None:
        return settings
    return settings.model_copy(update={"resolution_hours": resolution_hours})


def _scenario(paths: ProjectPaths, name: str) -> Scenario:
    try:
        return load_scenario(name, paths.config / "scenarios.yaml")
    except KeyError as exc:
        console.print(f"[red]{exc.args[0]}[/red]")
        raise typer.Exit(code=2) from exc


def _git_sha(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


@app.callback()
def _app_callback() -> None:
    """gb2035 command line."""


@app.command()
def version(root: RootOpt = Path()) -> None:
    console.print(__version__)


@app.command()
def scenarios(root: RootOpt = Path()) -> None:
    """List scenario names."""
    paths = ProjectPaths(root.resolve())
    for name in list_scenarios(paths.config / "scenarios.yaml"):
        console.print(name)


@app.command("config-show")
def config_show(scenario: ScenarioOpt, root: RootOpt = Path()) -> None:
    """Print the merged, validated scenario and settings."""
    paths, settings, _ = _ctx(root, None)
    sc = _scenario(paths, scenario)
    console.print_json(
        json.dumps(
            {"scenario": sc.model_dump(), "settings": settings.model_dump()}, indent=2, default=str
        )
    )


@app.command("retrieve")
def retrieve_cmd(
    root: RootOpt = Path(),
    only: Annotated[list[str] | None, typer.Option("--only", help="Manifest entry names.")] = None,
    pin: Annotated[
        bool, typer.Option("--pin", help="Record checksums for entries that lack one.")
    ] = False,
) -> None:
    """Download manifest entries into data/raw and verify checksums."""
    paths = ProjectPaths(root.resolve())
    entries = load_manifest(paths.manifest)
    reports = retrieve(entries, paths.data_raw, only=only, pin=pin)
    changed = False
    for r in reports:
        console.print(f"{r.action:10s} {r.name} ({r.size_bytes / 1e6:.1f} MB)")
        if r.action == "pinned":
            entries[r.name].sha256 = r.sha256
            entries[r.name].size_bytes = r.size_bytes
            changed = True
    if changed:
        save_manifest(paths.manifest, entries)
        console.print(f"manifest updated: {paths.manifest}")


@app.command("build-derived")
def build_derived(root: RootOpt = Path()) -> None:
    """Rebuild every committed table under data/derived from data/raw."""
    paths, settings, _ = _ctx(root, None)
    raw, derived = paths.data_raw, paths.data_derived
    derived.mkdir(parents=True, exist_ok=True)
    for name in [
        "buses.csv",
        "links.csv",
        "links_future.csv",
        "zone_definitions.csv",
        "zones.geojson",
        "transmission_grid_2030.yaml",
    ]:
        (derived / name).write_bytes((raw / name).read_bytes())
    zones = load_zones(derived / "zones.geojson")
    build_fleet_by_zone(
        raw / "power_stations_locations.csv", paths.config / "committed_plants.csv", zones
    ).to_csv(derived / "fleet_by_zone.csv", index=False, float_format="%.3f")
    build_repd_by_zone(raw / "REPD_Publication_Q2_2026.csv", zones).to_csv(
        derived / "repd_by_zone.csv", index=False, float_format="%.3f"
    )
    load_neso_demand(raw / "demanddata_2019.csv", settings.weather_year).to_frame().to_parquet(
        derived / "demand_2019_hourly.parquet"
    )
    extract_fes_2035(raw / "fes2025_data_workbook.xlsx").to_csv(
        derived / "fes2025_gb_2035.csv", index=False, float_format="%.3f"
    )
    build_costs(
        raw / "costs_2035.csv", paths.config / "costs_overrides.csv", settings.eur_to_gbp
    ).to_csv(derived / "costs_2035_gb.csv", float_format="%.3f")
    console.print(f"derived tables written to {derived}")


@app.command("build-profiles")
def build_profiles_cmd(
    cutout: Annotated[Path, typer.Option("--cutout")], root: RootOpt = Path()
) -> None:
    """Run atlite over the zone polygons (needs the `profiles` extra and the Zenodo cutout)."""
    from gb2035.data.profiles import build_profiles, flatten_columns, validate_profiles

    paths, settings, _ = _ctx(root, None)
    zones = load_zones(paths.data_derived / "zones.geojson")
    cf = build_profiles(cutout, zones)
    validate_profiles(cf, settings.weather_year)
    out = paths.data_derived / f"cf_{settings.weather_year}_zonal.parquet"
    flatten_columns(cf).to_parquet(out)
    console.print(f"profiles written to {out}")


def _build(paths: ProjectPaths, settings: Settings, scenario: Scenario) -> pypsa.Network:
    return build_network(load_inputs(paths), scenario, settings)


@app.command("build-network")
def build_network_cmd(
    scenario: ScenarioOpt,
    root: RootOpt = Path(),
    results_dir: ResultsOpt = None,
    resolution_hours: ResolutionHoursOpt = None,
) -> None:
    """Build and save the unsolved network."""
    paths, settings, results = _ctx(root, results_dir)
    settings = _with_resolution(settings, resolution_hours)
    sc = _scenario(paths, scenario)
    n = _build(paths, settings, sc)
    out = results / sc.name
    out.mkdir(parents=True, exist_ok=True)
    n.export_to_netcdf(out / "network_unsolved.nc")
    console.print(
        f"{len(n.buses)} buses, {len(n.generators)} generators, "
        f"{len(n.snapshots)} snapshots -> {out / 'network_unsolved.nc'}"
    )


def _run(paths: ProjectPaths, settings: Settings, sc: Scenario, results: Path) -> None:
    n = _build(paths, settings, sc)
    t0 = time.perf_counter()
    result = solve(n, settings)
    seconds = time.perf_counter() - t0
    out = results / sc.name
    write_results(extract_all(n, sc.name, result), out)
    n.export_to_netcdf(out / "network.nc")
    meta = {
        "scenario": sc.name,
        "git_sha": _git_sha(paths.root),
        "pypsa_version": pypsa.__version__,
        "solve_seconds": round(seconds, 1),
        "snapshots": len(n.snapshots),
        "resolution_hours": settings.resolution_hours,
        "total_cost_gbp_per_yr": result.total_cost_gbp_per_yr,
        "lp_objective_gbp_per_yr": result.lp_objective_gbp_per_yr,
        "fixed_asset_cost_gbp_per_yr": result.fixed_asset_cost_gbp_per_yr,
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    console.print(
        f"[green]{sc.name}[/green]: optimal in {seconds:.0f}s, "
        f"total cost {result.total_cost_gbp_per_yr / 1e9:.2f} bn GBP/yr -> {out}"
    )


@app.command("solve")
def solve_cmd(
    scenario: ScenarioOpt,
    root: RootOpt = Path(),
    results_dir: ResultsOpt = None,
    resolution_hours: ResolutionHoursOpt = None,
) -> None:
    """Build, solve and extract (alias of run)."""
    paths, settings, results = _ctx(root, results_dir)
    settings = _with_resolution(settings, resolution_hours)
    _run(paths, settings, _scenario(paths, scenario), results)


@app.command("run")
def run_cmd(
    scenario: ScenarioOpt,
    root: RootOpt = Path(),
    results_dir: ResultsOpt = None,
    resolution_hours: ResolutionHoursOpt = None,
) -> None:
    """Build, solve and extract one scenario."""
    paths, settings, results = _ctx(root, results_dir)
    settings = _with_resolution(settings, resolution_hours)
    _run(paths, settings, _scenario(paths, scenario), results)


@app.command("extract")
def extract_cmd(
    scenario: ScenarioOpt, root: RootOpt = Path(), results_dir: ResultsOpt = None
) -> None:
    """Re-extract tables from a saved solved network."""
    paths, _settings, results = _ctx(root, results_dir)
    sc = _scenario(paths, scenario)
    out = results / sc.name
    n = pypsa.Network(str(out / "network.nc"))
    constant = float(getattr(n, "objective_constant", 0.0) or 0.0)
    write_results(
        extract_all(
            n,
            sc.name,
            SolveResult(
                "ok",
                "optimal",
                float(cast(Any, n.objective)),
                constant,
                fixed_asset_cost_gbp_per_yr(n),
            ),
        ),
        out,
    )
    console.print(f"re-extracted {sc.name}")


@app.command("report")
def report_cmd(
    root: RootOpt = Path(),
    results_dir: ResultsOpt = None,
    update_readme_block: Annotated[bool, typer.Option("--update-readme")] = False,
) -> None:
    """Write results/summary.csv, README figures under docs/figures, and optionally the README
    table."""
    from gb2035.data.fes import load_fes
    from gb2035.report.figures import make_figures
    from gb2035.report.readme import summary_markdown, update_readme
    from gb2035.results.summary import summarise

    paths, _, results = _ctx(root, results_dir)
    path = write_summary(results)
    summary = summarise(results)
    console.print(f"summary -> {path}")
    if len(summary) and (results / "cap5").exists():
        figs = make_figures(
            summary,
            results,
            load_fes(paths.data_derived / "fes2025_gb_2035.csv"),
            paths.root / "docs" / "figures",
        )
        console.print(f"{len(figs)} figures -> docs/figures")
    if update_readme_block:
        update_readme(paths.root / "README.md", summary_markdown(summary))
        console.print("README summary block updated")
