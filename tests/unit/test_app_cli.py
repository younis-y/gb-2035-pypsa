import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from gb2035 import cli
from gb2035.cli import app

runner = CliRunner()


class FakeRun:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.calls: list[list[str]] = []
        self.cwds: list[object] = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        self.cwds.append(kwargs.get("cwd"))
        return subprocess.CompletedProcess(command, self.returncode)


def test_app_command_runs_streamlit_on_the_module(repo_root: Path, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(cli.subprocess, "run", fake)
    result = runner.invoke(app, ["app", "--root", str(repo_root)])
    assert result.exit_code == 0, result.stdout
    command = fake.calls[0]
    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert command[4].endswith(str(Path("gb2035") / "app" / "main.py"))
    assert Path(command[4]).exists()
    assert command[-2:] == ["--root", str(repo_root.resolve())]
    assert fake.cwds[0] == repo_root.resolve(), "the theme in .streamlit/ is read from the cwd"


def test_app_command_honours_port_and_address(repo_root: Path, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(cli.subprocess, "run", fake)
    result = runner.invoke(
        app, ["app", "--root", str(repo_root), "--port", "8600", "--address", "0.0.0.0"]
    )
    assert result.exit_code == 0
    command = fake.calls[0]
    assert "--server.port" in command and command[command.index("--server.port") + 1] == "8600"
    assert command[command.index("--server.address") + 1] == "0.0.0.0"


def test_app_command_propagates_a_failing_streamlit(repo_root: Path, monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", FakeRun(returncode=3))
    result = runner.invoke(app, ["app", "--root", str(repo_root)])
    assert result.exit_code == 3


def test_app_map_renders_the_same_figure_the_app_shows(
    repo_root: Path, tmp_path: Path, monkeypatch
):
    captured: dict[str, object] = {}

    def fake_write_image(figure, file, **kwargs):
        captured["traces"] = len(figure.data)
        captured["style"] = figure.layout.map.style
        captured["file"] = Path(file)
        Path(file).write_bytes(b"PNG")

    monkeypatch.setattr("plotly.io.write_image", fake_write_image)
    out = tmp_path / "app_map.png"
    result = runner.invoke(
        app, ["app-map", "--root", str(repo_root), "--scenario", "cap5", "--out", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert captured["file"] == out and out.exists()
    assert captured["style"]["sources"] == {}, "the export must not need a tile server"
    assert int(captured["traces"]) > 30, "one trace per corridor plus the four fixed layers"


def test_app_map_png_is_committed(repo_root: Path):
    """The README embeds this file; it must exist and be a real render, not a placeholder."""
    png = repo_root / "docs" / "figures" / "app_map.png"
    assert png.exists()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.stat().st_size > 50_000
