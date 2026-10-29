"""
Register authorship.lua as a Quarto filter. Run by great-docs before rendering.

great-docs writes _quarto.yml itself and has no setting for adding a filter, but Quarto
reads the project config again after its pre-render scripts have run, so adding the
filter here applies it to every page. great-docs copies docs/ to user-guide/ in the build
directory, which is where the filter is found.
"""

import pathlib

FILTER = "user-guide/assets/authorship.lua"

path = pathlib.Path("_quarto.yml")
text = path.read_text(encoding="utf-8")
if FILTER not in text:
    assert "\nfilters:\n" in text, "great-docs no longer writes a filters list to _quarto.yml"
    text = text.replace("\nfilters:\n", f"\nfilters:\n  - {FILTER}\n", 1)
    path.write_text(text, encoding="utf-8")
