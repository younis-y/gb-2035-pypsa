from pathlib import Path

import yaml

IMAGE = "ghcr.io/younis-y/gb-2035-pypsa"


def workflow(repo_root: Path) -> dict:
    # `on:` is YAML's boolean True, so read the file and look the key up by value.
    return yaml.safe_load((repo_root / ".github" / "workflows" / "docker.yml").read_text())


def test_docker_workflow_runs_on_pull_requests_and_main(repo_root: Path):
    triggers = workflow(repo_root)[True]
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers


def test_docker_workflow_may_write_packages(repo_root: Path):
    permissions = workflow(repo_root)["permissions"]
    assert permissions["packages"] == "write"
    assert permissions["contents"] == "read"


def test_docker_workflow_lints_builds_smoke_tests_then_pushes(repo_root: Path):
    steps = workflow(repo_root)["jobs"]["image"]["steps"]
    uses = [step.get("uses", "") for step in steps]
    assert any(u.startswith("hadolint/hadolint-action@") for u in uses)
    assert any(u.startswith("docker/metadata-action@") for u in uses)
    assert any(u.startswith("docker/login-action@") for u in uses)
    assert sum(u.startswith("docker/build-push-action@") for u in uses) == 2
    names = [step.get("name", "") for step in steps]
    assert names.index("Build the image") < names.index("Smoke-test the image")
    assert names.index("Smoke-test the image") < names.index("Push to GHCR")


def test_docker_workflow_tags_latest_and_the_short_sha(repo_root: Path):
    steps = workflow(repo_root)["jobs"]["image"]["steps"]
    meta = next(s for s in steps if s.get("uses", "").startswith("docker/metadata-action@"))
    assert meta["with"]["images"] == IMAGE
    assert "type=raw,value=latest,enable={{is_default_branch}}" in meta["with"]["tags"]
    assert "type=sha,format=short" in meta["with"]["tags"]


def test_pushing_steps_are_main_only(repo_root: Path):
    steps = workflow(repo_root)["jobs"]["image"]["steps"]
    for name in ("Log in to GHCR", "Push to GHCR"):
        step = next(s for s in steps if s.get("name") == name)
        assert step["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"


def test_readme_quotes_the_published_image(repo_root: Path):
    text = (repo_root / "README.md").read_text()
    assert f"docker run -p 8501:8501 {IMAGE}:latest" in text
    assert "## Run with Docker" in text
