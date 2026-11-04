"""
Add the authorship filter (quartopydoc's extension, installed in docs/_extensions/sciris
with `quarto add sciris/quartopydoc`) to the site that great-docs builds. Run by great-docs before rendering, in its build folder
(docs/_quarto/default).

great-docs has no setting for adding a filter, but Quarto reads the project config again
after its pre-render scripts have run, so naming the filter here applies it to every page.
It is named by path, not as an extension, because Quarto finds extensions before the
pre-render scripts run, and great-docs only copies its own into the build folder.
"""

import pathlib

FILTER = "../../_extensions/sciris/authorship/authorship.lua"

path = pathlib.Path("_quarto.yml")
text = path.read_text(encoding="utf-8")
if FILTER not in text:
    assert "\nfilters:\n" in text, "great-docs no longer writes a filters list to _quarto.yml"
    text = text.replace("\nfilters:\n", f"\nfilters:\n  - {FILTER}\n", 1)
    path.write_text(text, encoding="utf-8")
