from pathlib import Path

VIEWS = ("Overview", "Map", "Capacity and energy", "Teesside hydrogen", "Assumptions")
SOURCES = (
    "results/summary.csv",
    "capacities.csv",
    "duals.csv",
    "flows.csv",
    "energy.csv",
    "curtailment.csv",
    "hydrogen.csv",
    "config/assumptions.yaml",
    "data/derived/zones.geojson",
    "data/derived/buses.csv",
)


def test_docs_app_covers_every_view(repo_root: Path):
    text = (repo_root / "docs" / "app.md").read_text()
    for view in VIEWS:
        assert f"## {view}" in text, view


def test_docs_app_names_every_file_a_view_reads(repo_root: Path):
    text = (repo_root / "docs" / "app.md").read_text()
    assert [source for source in SOURCES if source not in text] == []


def test_docs_app_records_the_two_deviations_from_the_spec(repo_root: Path):
    text = (repo_root / "docs" / "app.md").read_text().lower()
    assert "folium" in text, "the spec named folium; say why the app uses plotly"
    assert "dispatch" in text, "the spec listed a dispatch page; say why it is not here"


def test_readme_links_the_page(repo_root: Path):
    assert "docs/app.md" in (repo_root / "README.md").read_text()
