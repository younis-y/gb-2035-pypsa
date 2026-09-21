"""Every read the app makes, and the caching that keeps a rerun cheap.

The `read_*` functions are pure: a path in, a DataFrame or dict out, no Streamlit involved, so
they are unit-testable on their own. The `load_*` names are the same functions wrapped in
`st.cache_data`, assigned rather than decorated so the pure function stays importable and mypy
strict stays happy whether or not the installed Streamlit ships type information.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

DEFAULT_SCENARIO = "cap5"
MARKER_FILES: tuple[str, ...] = ("config/scenarios.yaml", "results/summary.csv")


def find_project_root(start: Path) -> Path:
    """The nearest directory at or above `start` that holds every file in `MARKER_FILES`."""
    for candidate in (start, *start.parents):
        if all((candidate / rel).exists() for rel in MARKER_FILES):
            return candidate
    msg = f"no gb2035 project root at or above {start}: looked for {', '.join(MARKER_FILES)}"
    raise FileNotFoundError(msg)


def resolve_root(argv: Sequence[str], start: Path) -> Path:
    """`--root <path>` from `streamlit run main.py -- --root <path>`, else discovery.

    Streamlit passes everything after `--` through to the script, and `AppTest` passes nothing,
    so discovery is what runs under test and inside the container.
    """
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 < len(argv):
            return Path(argv[index + 1]).resolve()
    return find_project_root(start)
