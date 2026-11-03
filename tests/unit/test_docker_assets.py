from pathlib import Path


def test_dockerfile_builds_on_slim_python_with_a_pinned_uv(repo_root: Path):
    text = (repo_root / "Dockerfile").read_text()
    assert "FROM python:3.13-slim" in text
    assert "COPY --from=ghcr.io/astral-sh/uv:" in text
    assert "ghcr.io/astral-sh/uv:latest" not in text, "pin uv, do not float on latest"
    assert text.count("FROM ") >= 2, "multi-stage: build the venv, then copy it"


def test_dockerfile_installs_the_locked_app_extra_without_dev(repo_root: Path):
    text = (repo_root / "Dockerfile").read_text()
    assert "uv sync --frozen --no-dev --extra app" in text
    assert "--no-install-project" in text, "install dependencies in their own cached layer"


def test_dockerfile_serves_the_app_as_a_non_root_user(repo_root: Path):
    lines = [line.strip() for line in (repo_root / "Dockerfile").read_text().splitlines()]
    assert "EXPOSE 8501" in lines
    assert [line for line in lines if line.startswith("USER ")][-1] == "USER gb2035"
    healthcheck = next(line for line in lines if line.startswith("HEALTHCHECK"))
    assert "/_stcore/health" in "\n".join(lines[lines.index(healthcheck) :])
    # The healthcheck's own continuation line also starts with CMD; the image's command is the
    # last one.
    cmd = [line for line in lines if line.startswith("CMD ")][-1]
    assert "src/gb2035/app/main.py" in cmd
    assert "--server.address=0.0.0.0" in cmd
    assert "--server.port=8501" in cmd


def test_dockerignore_excludes_the_heavy_and_the_private(repo_root: Path):
    entries = {
        line.strip()
        for line in (repo_root / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for needed in (
        ".venv",
        ".git",
        ".worktrees",
        ".superpowers",
        "data/raw",
        "results/**/network.nc",
        "results/**/dispatch_hourly.parquet",
        "tests",
    ):
        assert needed in entries, needed


def test_dockerignore_keeps_what_the_image_needs(repo_root: Path):
    entries = {line.strip() for line in (repo_root / ".dockerignore").read_text().splitlines()}
    for kept in (
        "src",
        "config",
        "data/derived",
        "results",
        "uv.lock",
        "pyproject.toml",
        "README.md",
    ):
        assert kept not in entries, f"{kept} must reach the build context"
