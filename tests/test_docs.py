"""Tests for the documentation sources.

These do not build the site -- that needs Quarto, which is not a Python dependency. They
check the things that go stale silently: a page added without being wired into the
navigation, a cross-page link pointing at a file that no longer exists, and a code example
that no longer runs.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
SECTIONS = ("start", "data", "internals")

sys.path.insert(0, str(REPO / "scripts"))
import build_docs_theme as theme  # noqa: E402


def pages():
    return sorted(p for section in SECTIONS for p in (DOCS / section).glob("*.qmd"))


def test_every_section_has_pages():
    for section in SECTIONS:
        assert list((DOCS / section).glob("*.qmd")), f"docs/{section} is empty"


def test_generated_theme_is_up_to_date():
    """`assets/starsim-theme.html` carries the sidebar navigation, so it has to match."""
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "build_docs_theme.py"),
                             "--check"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_navigation_covers_every_page():
    listed = {page["href"] for section in theme.navigation() for page in section["pages"]}
    expected = {f"docs/{p.parent.name}/{re.sub(r'^[0-9]+-', '', p.stem)}.html" for p in pages()}
    assert listed == expected


def test_sections_match_the_great_docs_config():
    """The generated sidebar and the navbar must describe the same set of sections."""
    config = (REPO / "great-docs.yml").read_text()
    configured = re.findall(r"^\s*- title: (.+)\n\s*dir: docs/(\S+)", config, flags=re.M)
    assert [(t.strip(), d.strip()) for t, d in configured] == theme.SECTIONS


@pytest.mark.parametrize("page", pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_page_has_a_title(page):
    assert theme.page_title(page)


@pytest.mark.parametrize("page", pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_cross_page_links_resolve(page):
    """A link to a .qmd must point at a file that exists, allowing for the `NN-` prefix."""
    for target in re.findall(r"\]\((?!http)([^)#]+\.qmd)(?:#[^)]*)?\)", page.read_text()):
        resolved = (page.parent / target).resolve()
        if resolved.exists():
            continue
        # The URL drops the ordering prefix, so `tiers.qmd` means `NN-tiers.qmd`.
        matches = list(resolved.parent.glob(f"[0-9][0-9]-{resolved.name}"))
        assert matches, f"{page.name} links to {target}, which does not exist"


@pytest.mark.parametrize("page", pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_executable_cells_stay_offline(page):
    """Executed cells must not fetch anything, or building the docs would need a network.

    Examples that download are written as static ```python blocks instead.
    """
    for cell in re.findall(r"```\{python\}\n(.*?)```", page.read_text(), flags=re.S):
        # Strip string literals first: several pages tabulate these function names as
        # data, which is not the same as calling them.
        code = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cell)
        for call in ("ssd.fetch", "fetch_shapes(", "fetch_nodes(", "fetch_raster(",
                     "choropleth(", "cached_download("):
            assert call not in code, f"{page.name} executes {call!r} at build time"
