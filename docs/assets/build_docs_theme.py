"""
Generate the parts of the documentation site that should not be written by hand.

Dev/CI tool -- NOT part of the installed package. Run it after adding, renaming or moving
a page or a public function; `--check` is wired into the test suite and into the docs
workflow, so forgetting fails a test rather than silently producing a wrong site.

It rewrites one marked region of `great-docs.yml`, holding two things.

**`include_in_header`** -- a head snippet carrying three things the great-docs
configuration cannot express: the full site navigation in the left sidebar of every page
(great-docs otherwise gives each navbar section a sidebar containing only its own pages,
whereas the Starsim docs put the whole page list there, and the homepage gets none at
all); a Starsim-style footer; and a stylesheet fix so figures scale to the content column
instead of being clipped. It is inlined rather than kept beside this script because
great-docs copies only recognised asset files into its build directory, and a Quarto
`file:` include is resolved relative to that directory.

**`reference`** -- the API reference grouping, generated from each module's `__all__`, so
the only thing maintained by hand is one line per module in `GROUPS` below. Adding a
function to a module's `__all__` puts it in the documentation; removing one takes it out.
Nothing lists symbols individually, which matters because great-docs resolves those names
silently: a stale entry produces an empty page rather than an error.

Usage:

```bash
python docs/assets/build_docs_theme.py            # rewrite great-docs.yml
python docs/assets/build_docs_theme.py --check    # verify; write nothing
```
"""

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = REPO / "docs"
CONFIG = REPO / "great-docs.yml"

sys.path.insert(0, str(REPO))

# --- Narrative pages ---------------------------------------------------------------- #

# Section title -> directory under docs/, in navbar order. Must match `sections:` in
# great-docs.yml, which `tests/test_docs.py` checks.
SECTIONS = [
    ("Getting started", "start"),
    ("The data", "data"),
    ("Internals", "internals"),
]

# --- API reference ------------------------------------------------------------------ #

# Module -> (section title, description). Members come from each module's `__all__`, so
# this table is the whole of the hand-maintained reference configuration: one line per
# module, no symbol names. Modules are grouped by what a reader is trying to do rather
# than by Python type, which is what the module layout already encodes.
GROUPS = [
    ("loaders", "Loading bundled data",
     "Tier 0: everything inside the wheel. These never touch the network."),
    ("locations", "Locations",
     "Turning whatever a user typed into a canonical key, and the vocabulary for "
     "administrative levels."),
    ("nodes", "The node table",
     "Bundled subnational geography: where each administrative unit is, how big it is, "
     "and how far apart they are. No geospatial dependencies needed."),
    ("fetching", "Fetching UN WPP data",
     "Tier 2: annual series, complete life tables and other projection variants, "
     "downloaded on demand and cached."),
    ("shapes", "Boundaries",
     "Administrative boundaries with full geometry, from UNOCHA, geoBoundaries or GADM. "
     "Requires the [spatial] extra."),
    ("rasters", "Gridded population",
     "WorldPop rasters and their aggregation onto administrative units, which is what "
     "turns a boundary file into a metapopulation. Requires the [spatial] extra."),
    ("plotting", "Plotting",
     "Validation figures: the cheapest way to notice the wrong country or the wrong units."),
    ("cache", "Cache", "Where downloads go, what is in there, and how to change it."),
    ("settings", "Settings", "Package-level options, and how to set them."),
    ("registry", "The registry",
     "What datasets exist, how each one is shaped, and the hooks for adding your own."),
]

BEGIN = "# --- BEGIN GENERATED ---"
END = "# --- END GENERATED ---"

# --- Footer --------------------------------------------------------------------------#

COPYRIGHT = ("&copy; 2023&ndash;2026, Gates Foundation. All rights reserved. "
             '<a href="https://www.gatesfoundation.org/Privacy-and-Cookies-Notice">'
             "Privacy and Cookies Notice</a> | "
             '<a href="https://www.gatesfoundation.org/Terms-of-Use">Terms of Use</a>')
LINKS = [
    ("github", "https://github.com/starsimhub/starsim_data", "GitHub"),
    ("envelope-at-fill", "mailto:info@starsim.org", "Email"),
    ("slack", "https://starsim-idm.slack.com", "Slack"),
    ("globe", "https://starsim.org", "Starsim"),
]


def page_title(path):
    """Return a page's `title:` from its YAML frontmatter."""
    match = re.search(r'^title:\s*"?(.+?)"?\s*$', path.read_text(encoding="utf-8"), flags=re.M)
    if not match:
        raise SystemExit(f"{path} has no title in its frontmatter")
    return match.group(1)


def navigation():
    """Return `[{title, pages: [{href, title}]}]` for the section directories."""
    out = []
    for title, folder in SECTIONS:
        directory = DOCS / folder
        if not directory.is_dir():
            raise SystemExit(f"no such section directory: {directory}")
        pages = []
        for path in sorted(directory.glob("*.qmd")):
            slug = re.sub(r"^\d+-", "", path.stem)  # great-docs strips the ordering prefix
            pages.append(dict(href=f"docs/{folder}/{slug}.html", title=page_title(path)))
        if not pages:
            raise SystemExit(f"section {title!r} has no pages")
        out.append(dict(title=title, pages=pages))
    return out


def reference():
    """Return `[(title, desc, [names])]`, taking the members from each module's `__all__`."""
    package = importlib.import_module("starsim_data")
    exported = set(package.__all__)
    out = []
    for module_name, title, desc in GROUPS:
        module = importlib.import_module(f"starsim_data.{module_name}")
        names = []
        for name in module.__all__:
            # Prefer the top-level spelling where the package re-exports it, since that is
            # how a reader will write it; fall back to the qualified one otherwise.
            names.append(name if name in exported else f"{module_name}.{name}")
        if not names:
            raise SystemExit(f"starsim_data.{module_name} exports nothing")
        out.append((title, desc, names))
    return out


def render_reference(groups):
    """Return the YAML for the `reference:` block."""
    lines = ["reference:"]
    for title, desc, names in groups:
        lines.append(f"  - title: {title}")
        lines.append(f"    desc: >")
        for chunk in _wrap(desc, 84):
            lines.append(f"      {chunk}")
        lines.append("    contents:")
        lines += [f"      - {name}" for name in names]
        lines.append("")
    return "\n".join(lines)


def _wrap(text, width):
    """Wrap `text` to `width`, for readability of the generated YAML only."""
    words, line, out = text.split(), "", []
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def render_header(nav):
    """Return the `include_in_header` YAML, with the snippet as a block scalar."""
    snippet = render_snippet(nav)
    body = "\n".join(f"      {line}".rstrip() for line in snippet.splitlines())
    return "include_in_header:\n  - text: |\n" + body + "\n"


def render_snippet(nav):
    """Return the head snippet: the figure fix, the sidebar script and the footer."""
    # Joined without newlines: this is interpolated into a JavaScript string literal, and
    # a raw newline inside one is a syntax error.
    icons = "".join(f'<a href="{href}" title="{label}" aria-label="{label}">'
                    f'<i class="bi bi-{icon}"></i></a>' for icon, href, label in LINKS)
    return f"""<style>
  /* Matplotlib figures are emitted at their native pixel size, which for a multi-panel
     figure is wider than the content column. !important because the theme stylesheet
     loads after this block and sets max-width: none. */
  img.figure-img,
  .cell-output-display img {{
    max-width: 100% !important;
    height: auto !important;
  }}
  /* Section headings in the rebuilt sidebar. */
  .gd-nav-heading {{
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    opacity: 0.65;
    margin: 1.1rem 0 0.3rem 0;
  }}
  .gd-nav-heading:first-child {{ margin-top: 0.25rem; }}
  /* The homepage has no sidebar of its own, so one is added in the empty left margin.
     Hidden on narrow screens, where that margin does not exist. */
  .gd-home-nav {{
    position: fixed;
    top: 5.2rem;
    left: 0;
    width: 20rem;
    max-height: calc(100vh - 6rem);
    overflow-y: auto;
    padding: 0.5rem 1rem 2rem 2rem;
    font-size: 0.95rem;
    z-index: 100;
  }}
  .gd-home-nav a {{ text-decoration: none; }}
  .gd-home-nav a:hover {{ text-decoration: underline; }}
  .gd-home-nav ul {{ list-style: none; padding-left: 0; margin: 0 0 0.25rem 0; }}
  .gd-home-nav li {{ padding: 0.12rem 0; }}
  @media (max-width: 1400px) {{ .gd-home-nav {{ display: none; }} }}
  /* Footer: centred text, icons on the right, matching the other Starsim sites. */
  footer.footer .nav-footer {{ display: flex; align-items: center; gap: 1rem; }}
  footer.footer .nav-footer-center {{ flex: 1 1 auto; }}
  footer.footer .nav-footer-center p {{ text-align: center !important; margin: 0; }}
  footer.footer .nav-footer-right {{ flex: 0 0 auto; display: flex; gap: 0.75rem; font-size: 1.1rem; }}
  @media (max-width: 700px) {{
    footer.footer .nav-footer {{ flex-direction: column; }}
  }}
</style>
<script>
(function () {{
  var NAV = {json.dumps(nav, indent=2)};

  function siteRoot() {{
    // The navbar brand always points at the site root, which is the only reliable way to
    // build absolute URLs when the site may be served from a subdirectory.
    var brand = document.querySelector('.navbar-brand, a.navbar-brand');
    if (!brand) return null;
    return brand.href.replace(/index\\.html?$/, '').replace(/\\/?$/, '/');
  }}

  function navHtml(root, here, headingClass) {{
    var html = '';
    NAV.forEach(function (section) {{
      html += '<div class="' + headingClass + '">' + section.title + '</div>';
      html += '<ul class="list-unstyled mt-1">';
      section.pages.forEach(function (page) {{
        var url = new URL(page.href, root);
        var active = url.pathname === here ? ' active' : '';
        html += '<li class="sidebar-item"><div class="sidebar-item-container">' +
                '<a href="' + url.href + '" class="sidebar-item-text sidebar-link' + active +
                '"><span class="menu-text">' + page.title + '</span></a></div></li>';
      }});
      html += '</ul>';
    }});
    return html;
  }}

  function isGuidePage(root, here) {{
    return NAV.some(function (s) {{
      return s.pages.some(function (p) {{ return new URL(p.href, root).pathname === here; }});
    }});
  }}

  function buildSidebar(root, here) {{
    var container = document.querySelector('#quarto-sidebar .sidebar-menu-container');
    // Only take over the sidebar on guide pages; Reference pages keep their API
    // navigation, as they do in the Starsim docs.
    if (!container || !isGuidePage(root, here)) return;
    container.innerHTML = navHtml(root, here, 'gd-nav-heading');
  }}

  function buildHomeNav(root, here) {{
    // The homepage is generated from the README and has no sidebar element at all, so
    // add one rather than filling one in.
    if (!document.body.classList.contains('gd-homepage')) return;
    if (document.querySelector('.gd-home-nav')) return;
    var nav = document.createElement('nav');
    nav.className = 'gd-home-nav';
    nav.setAttribute('aria-label', 'Site navigation');
    nav.innerHTML = navHtml(root, here, 'gd-nav-heading');
    document.body.appendChild(nav);
  }}

  function buildFooter() {{
    var footer = document.querySelector('footer.footer .nav-footer');
    if (!footer) return;
    footer.innerHTML =
      '<div class="nav-footer-center"><p>{COPYRIGHT}</p></div>' +
      '<div class="nav-footer-right">{icons}</div>';
  }}

  function apply() {{
    var root = siteRoot();
    if (!root) return;
    var here = window.location.pathname.replace(/\\/$/, '');
    buildSidebar(root, here);
    buildHomeNav(root, here);
    buildFooter();
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', apply);
  }} else {{
    apply();
  }}
}})();
</script>
"""


def render(nav, groups):
    """Return the whole generated region of `great-docs.yml`."""
    return "\n".join([
        BEGIN,
        "# Everything between these markers is generated by",
        "# docs/assets/build_docs_theme.py. Edit that script, not this block.",
        "",
        render_header(nav),
        render_reference(groups),
        END,
    ])


def splice(config, block):
    """Return `config` with the generated region replaced by `block`."""
    if BEGIN not in config or END not in config:
        raise SystemExit(f"{CONFIG.name} has no {BEGIN} / {END} markers to write between")
    head, rest = config.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return head + block + tail


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="verify the generated region is up to date; write nothing")
    args = parser.parse_args()

    nav = navigation()
    groups = reference()
    current = CONFIG.read_text(encoding="utf-8")
    wanted = splice(current, render(nav, groups))

    pages = sum(len(s["pages"]) for s in nav)
    symbols = sum(len(names) for _, _, names in groups)

    if args.check:
        if current != wanted:
            raise SystemExit(f"the generated region of {CONFIG.name} is out of date; "
                             f"regenerate it with:\n  python docs/assets/build_docs_theme.py")
        print(f"Up to date: {pages} pages in {len(nav)} sections, "
              f"{symbols} symbols in {len(groups)} reference groups.")
        return

    CONFIG.write_text(wanted, encoding="utf-8")
    print(f"Rewrote the generated region of {CONFIG.name}")
    for section in nav:
        print(f"  {section['title']}: " + ", ".join(p["title"] for p in section["pages"]))
    for title, _, names in groups:
        print(f"  {title}: {len(names)} symbol(s)")


if __name__ == "__main__":
    sys.exit(main())
