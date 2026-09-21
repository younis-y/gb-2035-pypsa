from pathlib import Path

import pytest

from gb2035.data.costs import (
    annuity,
    battery_capital_cost_per_mw_yr,
    build_costs,
    capital_cost_per_yr,
    load_costs,
)


def test_annuity():
    assert annuity(0.07, 25) == pytest.approx(0.08581, abs=1e-4)
    assert annuity(0.0, 20) == pytest.approx(0.05)


def test_build_costs_converts_and_overrides(fixtures_dir: Path, tmp_path: Path):
    overrides = tmp_path / "ov.csv"
    overrides.write_text(
        "technology,parameter,value,unit,source\n"
        "onwind,capex_gbp,1280000,GBP/MW,DESNZ\n"
        "gas_ccs,capex_gbp,2220000,GBP/MW,DESNZ\n"
        "gas_ccs,fom_gbp_per_yr,35500,GBP/MW/yr,DESNZ\n"
        "gas_ccs,vom_gbp_per_mwh,6,GBP/MWh,DESNZ\n"
        "gas_ccs,efficiency,0.47,ratio,DESNZ\n"
        "gas_ccs,lifetime_yr,25,years,DESNZ\n"
    )
    c = build_costs(fixtures_dir / "technology_data_sample.csv", overrides, eur_to_gbp=0.85)
    assert c.loc["onwind", "capex_gbp"] == 1_280_000, "override wins"
    assert c.loc["onwind", "fom_gbp_per_yr"] == pytest.approx(1000 * 1000 * 0.85 * 0.02), (
        "FOM percent applies to the technology-data capex before override"
    )
    assert c.loc["onwind", "vom_gbp_per_mwh"] == pytest.approx(0.85)
    assert (
        c.loc["battery_storage", "capex_gbp"] == pytest.approx(100 * 1000 * 0.85)
        and c.loc["battery_storage", "capex_basis"] == "MWh"
    )
    assert (
        c.loc["hvdc_submarine", "capex_gbp"] == pytest.approx(3000 * 0.85)
        and c.loc["hvdc_submarine", "capex_basis"] == "MW-km"
    )
    assert c.loc["electrolysis", "efficiency"] == 0.64
    assert c.loc["gas_ccs", "capex_gbp"] == 2_220_000 and c.loc["gas_ccs", "capex_basis"] == "MW"
    assert "DESNZ" in c.loc["gas_ccs", "source"]


def test_sources_accumulate_across_overrides(fixtures_dir: Path, tmp_path: Path):
    overrides = tmp_path / "ov.csv"
    overrides.write_text(
        "technology,parameter,value,unit,source\n"
        "onwind,capex_gbp,1280000,GBP/MW,DESNZ capex\n"
        "onwind,lifetime_yr,35,years,DESNZ lifetime\n"
        "ccgt_existing,fom_gbp_per_yr,22900,GBP/MW/yr,DESNZ fixed costs\n"
        "ccgt_existing,lifetime_yr,25,years,not used (no capex)\n"
    )
    c = build_costs(fixtures_dir / "technology_data_sample.csv", overrides, eur_to_gbp=0.85)
    assert "PyPSA technology-data" in c.loc["onwind", "source"]
    assert (
        "DESNZ capex" in c.loc["onwind", "source"] and "DESNZ lifetime" in c.loc["onwind", "source"]
    )
    assert "DESNZ fixed costs" in c.loc["ccgt_existing", "source"]
    assert (
        "currency year 2025 " in c.loc["onwind", "source"]
        or "currency year 2025)" in c.loc["onwind", "source"]
    )


def test_capital_cost_helpers(fixtures_dir: Path, tmp_path: Path):
    overrides = tmp_path / "ov.csv"
    overrides.write_text("technology,parameter,value,unit,source\n")
    c = build_costs(fixtures_dir / "technology_data_sample.csv", overrides, eur_to_gbp=1.0)
    assert capital_cost_per_yr(c, "onwind", 0.07) == pytest.approx(
        annuity(0.07, 30) * 1_000_000 + 20_000
    )
    expected = annuity(0.07, 10) * 200_000 + 2_000 + 2 * annuity(0.07, 20) * 100_000
    assert battery_capital_cost_per_mw_yr(c, hours=2, rate=0.07) == pytest.approx(expected)


def test_committed_costs_table(repo_root: Path):
    c = load_costs(repo_root / "data" / "derived" / "costs_2035_gb.csv")
    for tech in [
        "onwind",
        "offwind",
        "solar",
        "nuclear",
        "ccgt",
        "ccgt_existing",
        "ocgt",
        "gas_ccs",
        "h2_ccgt",
        "battery_inverter",
        "battery_storage",
        "electrolysis",
        "h2_store",
        "hvdc_submarine",
        "hvac_overhead",
    ]:
        assert tech in c.index, tech
    assert c.loc["onwind", "capex_gbp"] == 1_280_000
    assert c.loc["electrolysis", "capex_gbp"] == pytest.approx(1697.4017 * 1000 * 0.85, rel=1e-4)
    assert c.loc["h2_store", "capex_gbp"] == pytest.approx(2.3398 * 1000 * 0.85, rel=1e-3)
    assert (c["source"].str.len() > 0).all()
    assert "DESNZ" in c.loc["ccgt_existing", "source"]
    assert "technology-data" in c.loc["onwind", "source"]
