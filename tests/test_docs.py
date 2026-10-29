"""
Test the documentation sources.

These do not build the site -- that needs Quarto, which is not a Python dependency. They
check the things that would otherwise go stale silently: a page missing the frontmatter
that puts it in the sidebar, a cross-page link pointing at a file that no longer exists,
and an executed code example that would make the build reach for the network.

There is nothing here about the sidebar or the API reference. great-docs builds both
itself, from the `guide-section` frontmatter and from the public API, so there is no
generated configuration to keep in step with the code.
"""

import re

import sciris as sc
import yaml

REPO = sc.thispath(__file__).parent
DOCS = REPO / "docs" / "user-guide"

# The sidebar groups, in the order the pages' filename prefixes put them in.
SECTIONS = ["Getting started", "The data", "Internals"]


def pages():
    """ The narrative pages, in filename order """
    return sorted(DOCS.glob("*.qmd"))


def frontmatter(path):
    """ A page's YAML frontmatter, as a dict """
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), flags=re.S)
    assert match, f"{path.name} has no YAML frontmatter"
    return yaml.safe_load(match.group(1))


@sc.timer()
def test_pages():
    """ Every page has a title and a section, and the sections are contiguous """
    sc.heading("Testing page frontmatter")
    assert len(pages()) >= 9 # The narrative pages exist

    # `title` is the sidebar label and `guide-section` is the group it appears under
    for page in pages():
        meta = frontmatter(page)
        assert meta.get("title"), f"{page.name} has no title"
        assert meta.get("guide-section") in SECTIONS, f"{page.name}: guide-section must be one of {SECTIONS}"

    # Pages are ordered by filename, so a section must not be split by another one
    seen = [frontmatter(p)["guide-section"] for p in pages()]
    ordered = [s for i, s in enumerate(seen) if i == 0 or s != seen[i - 1]]
    assert ordered == SECTIONS, f"section order is {ordered}, expected {SECTIONS}"
    return seen


@sc.timer()
def test_links():
    """
    Links point at real pages, allowing for the numeric prefix and the landing page.

    The first page is the site landing page: it renders at the site root while its
    siblings render under `user-guide/`, so its links carry that prefix. Every other page
    links to plain siblings.
    """
    sc.heading("Testing cross-page links")
    for page in pages():
        for target in re.findall(r"\]\((?!http)([^)#]+\.qmd)(?:#[^)]*)?\)", page.read_text()):
            name = target.removeprefix("user-guide/")
            assert "/" not in name, f"{page.name} links to {target}, which is not a guide page"
            assert list(DOCS.glob(f"[0-9][0-9]-{name}")), f"{page.name} links to {target}, which does not exist"

    # A `user-guide/` prefix on any other page would be a broken link
    for page in pages()[1:]:
        assert "](user-guide/" not in page.read_text(), f"{page.name} should link to plain siblings, not via user-guide/"
    assert "](user-guide/" in pages()[0].read_text() # The landing page does use it


@sc.timer()
def test_offline():
    """
    Executed cells must not fetch anything, or building the docs would need a network.

    Examples that download are written as static ```python blocks instead.
    """
    sc.heading("Testing that executed cells stay offline")
    calls = ("ssd.fetch", "fetch_shapes(", "fetch_nodes(", "fetch_raster(", "choropleth(", "cached_download(")
    for page in pages():
        for cell in re.findall(r"```\{python\}\n(.*?)```", page.read_text(), flags=re.S):
            # Strip string literals first: several pages tabulate these function names as
            # data, which is not the same as calling them
            code = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cell)
            for call in calls:
                assert call not in code, f"{page.name} executes {call!r} at build time"


@sc.timer()
def test_config():
    """
    The sidebar and the reference must stay great-docs' job rather than ours.

    If either needed configuring by hand it would need keeping in step with the code,
    which is exactly what this arrangement exists to avoid.
    """
    sc.heading("Testing the great-docs config")
    config = yaml.safe_load((REPO / "docs" / "great-docs.yml").read_text())
    assert config["user_guide"] == "user-guide" # The narrative pages live in docs/user-guide/
    assert config["homepage"] == "user_guide" # And the first is the landing page
    assert "sections" not in config, "sections would give each group its own sidebar"
    # `title` is fine; `contents` or `sections` would mean listing symbols by hand
    reference = config.get("reference", {})
    assert set(reference) <= {"title", "desc"}, "the API reference should be discovered, not listed"
    return config


if __name__ == "__main__":
    T = sc.timer()

    sections = test_pages()
    test_links()
    test_offline()
    config = test_config()

    T.toc()
