"""Tests for the documentation sources.

These do not build the site -- that needs Quarto, which is not a Python dependency. They
check the things that would otherwise go stale silently: a page missing the frontmatter
that puts it in the sidebar, a cross-page link pointing at a file that no longer exists,
and an executed code example that would make the build reach for the network.

There is nothing here about the sidebar or the API reference. great-docs builds both
itself, from the `guide-section` frontmatter and from the public API, so there is no
generated configuration to keep in step with the code.
"""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

# The sidebar groups, in the order the pages' filename prefixes put them in.
SECTIONS = ["Getting started", "The data", "Internals"]


def pages():
    return sorted(DOCS.glob("*.qmd"))


def frontmatter(path):
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), flags=re.S)
    assert match, f"{path.name} has no YAML frontmatter"
    return yaml.safe_load(match.group(1))


def test_pages_exist():
    assert len(pages()) >= 9


@pytest.mark.parametrize("page", pages(), ids=lambda p: p.name)
def test_page_has_title_and_section(page):
    """`title` is the sidebar label and `guide-section` is the group it appears under."""
    meta = frontmatter(page)
    assert meta.get("title")
    assert meta.get("guide-section") in SECTIONS, \
        f"{page.name}: guide-section must be one of {SECTIONS}"


def test_sections_are_contiguous():
    """Pages are ordered by filename, so a section must not be split by another one."""
    seen = [frontmatter(p)["guide-section"] for p in pages()]
    ordered = [s for i, s in enumerate(seen) if i == 0 or s != seen[i - 1]]
    assert ordered == SECTIONS, f"section order is {ordered}, expected {SECTIONS}"


@pytest.mark.parametrize("page", pages(), ids=lambda p: p.name)
def test_cross_page_links_resolve(page):
    """Links point at real pages, allowing for the numeric prefix and the landing page.

    The first page is the site landing page: it renders at the site root while its
    siblings render under `user-guide/`, so its links carry that prefix. Every other page
    links to plain siblings.
    """
    for target in re.findall(r"\]\((?!http)([^)#]+\.qmd)(?:#[^)]*)?\)", page.read_text()):
        name = target.removeprefix("user-guide/")
        assert "/" not in name, f"{page.name} links to {target}, which is not a guide page"
        assert list(DOCS.glob(f"[0-9][0-9]-{name}")), \
            f"{page.name} links to {target}, which does not exist"


def test_only_the_landing_page_uses_the_user_guide_prefix():
    """A `user-guide/` prefix on any other page would be a broken link."""
    for page in pages()[1:]:
        assert "](user-guide/" not in page.read_text(), \
            f"{page.name} should link to plain siblings, not via user-guide/"
    assert "](user-guide/" in pages()[0].read_text()


@pytest.mark.parametrize("page", pages(), ids=lambda p: p.name)
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


def test_config_uses_native_navigation():
    """The sidebar and the reference must stay great-docs' job rather than ours.

    If either needed configuring by hand it would need keeping in step with the code,
    which is exactly what this arrangement exists to avoid.
    """
    config = yaml.safe_load((REPO / "great-docs.yml").read_text())
    assert config["user_guide"] == "docs"
    assert config["homepage"] == "user_guide"
    assert "reference" not in config, "the API reference should be discovered, not listed"
    assert "sections" not in config, "sections would give each group its own sidebar"
