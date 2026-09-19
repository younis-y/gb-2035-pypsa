Generated from `config/assumptions.yaml` by `gb2035 report --update-readme`.

| Key | Value | Unit | Confidence | Source |
|---|---|---|---|---|
| battery_round_trip_efficiency | 0.9 | ratio | published | younis-y/gb-weather-to-price-forecasting scripts/03_price_prediction_main.py EFFICIENCY_RTE |
| battery_wear_cost_gbp_mwh | 0.09 | GBP/MWh | derived | 0.1 EUR/MWh DEGRADATION_COST in the same script, converted at 0.85 |
| blue_h2_co2_t_per_mwh | 0.02 | tCO2/MWh H2 | derived | Derived: 0.27 tCO2/MWh H2 direct emissions from natural gas reforming at 95 percent capture |
| blue_h2_cost_gbp_mwh | 70 | GBP/MWh H2 | assumption | DESNZ Hydrogen production costs 2021, CCUS-enabled range for 2035, upper-middle |
| blue_h2_max_mw | 1200 | MW H2 | published | bp H2Teesside planned 1.2 GW hydrogen output (bp, 2025) |
| ccs_transport_storage_gbp_t | 9 | GBP/tCO2 | published | DESNZ Electricity Generation Costs 2025 Annex A, Gas CCUS 2035, CO2 capture and storage cost |
| discount_rate | 0.07 | ratio | assumption | Author assumption; DESNZ 2025 hurdle rates span 0.076 to 0.101 |
| dri_electricity_mwh_per_t | 0.7 | MWh per t steel | published | Vogl, Ahman and Nilsson 2018: hydrogen-DRI-EAF electricity excluding electrolysis |
| electrolysis_efficiency | 0.67 | ratio LHV | derived | PyPSA technology-data v0.15.0 electrolysis 2035 (0.637) and PyPSA-GB hydrogen rule (0.70); midpoint |
| ets_price_gbp_t | 55 | GBP/tCO2 | published | UK ETS allowance price, mid-2025 market level |
| eur_to_gbp | 0.85 | GBP per EUR | published | ECB euro reference rate, 2025 annual average |
| gas_ccs_capture_rate | 0.9 | ratio | published | PyPSA technology-data v0.15.0, CCGT capture rate |
| gas_co2_t_per_mwh_th | 0.184 | tCO2/MWh thermal | published | DESNZ Greenhouse gas reporting conversion factors 2024, natural gas gross CV |
| gas_price_gbp_mwh_th | 24 | GBP/MWh thermal | published | DESNZ Fossil fuel price assumptions 2024, central gas 2035 (https://www.gov.uk/government/publications/fossil-fuel-price-assumptions-2024) |
| h2_dri_kg_per_t | 51 | kg H2 per t steel | published | Vogl, Ahman and Nilsson 2018, Journal of Cleaner Production 203 |
| h2_dri_mt_steel | 3 | Mt per year | assumption | Tata Steel Port Talbot EAF nameplate 3 Mt/yr, used as the hydrogen-DRI sensitivity tonnage |
| h2_lhv_mwh_per_t | 33.33 | MWh per t H2 | published | Hydrogen lower heating value 120 MJ/kg = 33.33 kWh/kg |
| hydrogen_turbine_efficiency | 0.5 | ratio | published | PyPSA-GB rules/hydrogen.smk (0.50); DESNZ 2025 CCHT 2035 gives 0.51 |
| interconnector_export_price_gbp_mwh | 45 | GBP/MWh | assumption | Author assumption: GB renewable surplus coincides with neighbours' surplus, so exports clear below the import price; 45 sits at about 70 percent of the 65 GBP/MWh import assumption |
| interconnector_import_price_gbp_mwh | 65 | GBP/MWh | assumption | Author assumption: rounded 2024 GB day-ahead annual mean (Elexon MID APX series) |
| interconnector_price_sensitivity_gbp_mwh | 100 | GBP/MWh | assumption | Author assumption: stress value above the 2024 GB day-ahead mean, in line with 2022 to 2023 price levels |
| interconnector_total_gw | 19.4 | GW | published | FES 2025 Data Workbook V006, sheet F.61, Holistic Transition 2035 |
| losses_uplift | 1.07 | ratio | derived | FES 2025 Data Workbook V006, sheets F.53 and DB.ED1 (https://www.neso.energy/document/364551/download) |
| nuclear_2035_gw | 5.04 | GW | published | FES 2025 F.62 Holistic Transition 2035 |
| offshore_cap_national_gw | 150 | GW | assumption | Author assumption informed by the Crown Estate leasing pipeline and FES 2025 F.55 (86.1 GW HT 2035) |
| offwind_share_dogger_bank | 0.35 | ratio | assumption | Author assumption informed by Crown Estate Round 4 and ScotWind leasing geography and FES 2025 F.55 (86.1 GW HT 2035) |
| offwind_share_east_anglia | 0.25 | ratio | assumption | Author assumption informed by Crown Estate Round 4 and ScotWind leasing geography and FES 2025 F.55 (86.1 GW HT 2035) |
| offwind_share_hornsea | 0.25 | ratio | assumption | Author assumption informed by Crown Estate Round 4 and ScotWind leasing geography and FES 2025 F.55 (86.1 GW HT 2035) |
| offwind_share_other_coastal | 0.15 | ratio | assumption | Author assumption informed by Crown Estate Round 4 and ScotWind leasing geography and FES 2025 F.55 (86.1 GW HT 2035) |
| onshore_cap_national_gw | 60 | GW | assumption | Author assumption informed by FES 2025 F.56 (38.4 GW HT 2035) and younis-y/uk-onshore-wind-siting |
| port_talbot_eaf_twh | 1.5 | TWh/yr | derived | Tata Steel 3 Mt/yr EAF x 0.5 MWh/t |
| power_sector_emissions_2024_mt | 37.5 | MtCO2e | published | DESNZ 2024 UK greenhouse gas emissions provisional figures, electricity supply |
| pumped_hydro_hours | 8 | hours | assumption | Dinorwig 1,728 MW / 9.1 GWh about 5 h and Cruachan 440 MW about 10 h; fleet average, author assumption |
| pumped_hydro_round_trip_efficiency | 0.75 | ratio | assumption | Author assumption: 70 to 80 percent typical for GB pumped storage |
| scunthorpe_eaf_twh | 1.5 | TWh/yr | assumption | Author assumption: consented EAF plan capacity unconfirmed; mirrors Port Talbot |
| solar_cap_national_gw | 150 | GW | assumption | Author assumption informed by FES 2025 F.57 (61.8 GW HT 2035) |
| solver_tolerance | 1e-05 | ratio | assumption | HiGHS PDLP primal/dual feasibility tolerance; simplex needs 20 min for four weeks and hours for a year on this LP |
| teesside_committed_electrolysis_mw | 0 | MW | published | bp cancelled HyGreen Teesside, 4 March 2025 (Energy Voice report) |
| teesside_industrial_h2_twh_ee | 1.3 | TWh/yr | derived | FES 2025 F.51 industrial hydrogen demand EE 2035 (5.14 TWh) x 0.25 |
| teesside_industrial_h2_twh_ht | 5 | TWh/yr | derived | FES 2025 F.51 industrial hydrogen demand HT 2035 (19.79 TWh) x 0.25 |
| teesside_share_of_uk_hydrogen | 0.25 | ratio | published | Tees Valley Combined Authority hydrogen strategy key findings 2023: up to 2.5 GW of the UK 10 GW 2030 ambition |
