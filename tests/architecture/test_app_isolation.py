import re
import subprocess
import sys
from pathlib import Path

SOLVER_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:pypsa|linopy|highspy)\b", re.MULTILINE)
MODEL_IMPORT = re.compile(r"^\s*(?:import|from)\s+gb2035\.model\b", re.MULTILINE)


def offenders(repo_root: Path, pattern: re.Pattern[str]) -> list[str]:
    return [
        str(path.relative_to(repo_root))
        for path in sorted((repo_root / "src" / "gb2035" / "app").rglob("*.py"))
        if pattern.search(path.read_text())
    ]


def test_app_never_imports_the_solver_stack(repo_root: Path):
    assert offenders(repo_root, SOLVER_IMPORT) == [], (
        "the app reads committed CSVs; it must never import pypsa, linopy or highspy"
    )


def test_app_never_imports_the_model_layer(repo_root: Path):
    assert offenders(repo_root, MODEL_IMPORT) == []


def test_importing_the_app_does_not_pull_in_the_solver_stack():
    """The regexes above miss transitive imports; this catches them at runtime."""
    code = (
        "import sys; import gb2035.app.data; "
        "print(sorted(m for m in ('pypsa', 'linopy', 'highspy') if m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", result.stdout
