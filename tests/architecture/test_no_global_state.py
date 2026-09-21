import re
from pathlib import Path

import yaml

FORBIDDEN = re.compile(r"os\.environ|dotenv|load_settings\(|load_scenario\(|load_assumptions\(")


def test_core_modules_take_parameters_not_globals(repo_root: Path):
    offenders = []
    for sub in ("data", "model", "results"):
        for path in (repo_root / "src" / "gb2035" / sub).rglob("*.py"):
            if FORBIDDEN.search(path.read_text()):
                offenders.append(str(path.relative_to(repo_root)))
    assert offenders == [], f"core modules must receive config as arguments: {offenders}"


def test_every_assumption_has_a_source(repo_root: Path):
    doc = yaml.safe_load((repo_root / "config" / "assumptions.yaml").read_text())
    missing = [k for k, v in doc.items() if not str(v.get("source", "")).strip()]
    assert missing == []
