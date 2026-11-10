import re
from pathlib import Path

LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def test_every_relative_link_in_the_docs_resolves(repo_root: Path):
    pages = [repo_root / "README.md", *sorted((repo_root / "docs").glob("*.md"))]
    broken = [
        f"{page.relative_to(repo_root)} -> {target}"
        for page in pages
        for target in LINK.findall(page.read_text())
        if not target.startswith(("http://", "https://", "mailto:"))
        and not (page.parent / target).exists()
    ]
    assert broken == []
