# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`starsim_data` distributes UN WPP demographics, contact matrices, and administrative geography for [Starsim](https://starsim.org) models. It returns dataframes and nothing else — no model code, no simulation logic. See `docs/07-related-projects.qmd` for where that line is drawn and why.

## Commands

```bash
pip install -e ".[dev]"              # runtime + pytest + pycountry + great-docs
pip install -e ".[dev,spatial]"      # also geopandas/pyogrio/rastertoolkit, needed by build_nodes.py

pytest                               # the offline suite
pytest -m "not network"              # what CI runs
pytest -m network                    # also hits UN/WorldPop servers (a few hundred MB)
pytest tests/test_load.py -k matrix  # one file, one pattern
pytest tests/test_load.py::test_mistry_matrix_shape

great-docs build                     # -> great-docs/_site/ (needs Quarto)
great-docs preview                   # live reload on localhost:3000
```

Markers are declared in `pyproject.toml`: `network`, `slow`, `integration`, `spatial` (the last skips automatically without the extra). `tests/conftest.py` redirects the cache to a temp dir so tests never touch the user's real one; set `STARSIM_DATA_CACHE_DIR` to reuse downloads across network-test runs.

### Rebuilding the bundled data

The `.h5` files in `starsim_data/data/` are **committed build artifacts**, generated from `raw_data/` by `scripts/`. Never hand-edit them. Every script takes `--check` (validate without writing), which is what CI runs to stop the artifacts drifting from their sources:

```bash
python scripts/build_locations.py --check     # derived columns of locations.csv, from pycountry
python scripts/build_hdf5.py --check          # prem2021.h5 and data/fetched.json, from raw_data/contact_matrices/ (--fetched also rebuilds fetched/*.h5)
python scripts/build_demographics.py --check  # demographics, from raw_data/demographics/
python scripts/build_nodes.py --check         # node table; ~420 MB cold, [spatial] required
python scripts/build_nodes.py --limit 5       # a quick subset while developing
python scripts/download_wpp.py                # refresh raw_data/demographics/ (needs a token in scripts/.env)
```

`build_nodes.py` is excluded from the per-PR CI job because of its size; it has a `workflow_dispatch`-only job in `.github/workflows/tests.yml`.

## Architecture

### The tier invariant

Every function belongs to exactly one tier, and this is the design constraint the rest of the package is arranged around:

- **Tier 0** — `load()`, `load_nodes()`, `distances()`. Reads only what is inside the wheel. **Never touches the network**, so it is instant, offline and byte-identical for everyone on a given version.
- **Tier 1** — `fetch()`, `fetch_shapes()`, `fetch_nodes()`, `fetch_raster()`. Downloads and caches, with a provenance sidecar per file.

Tier is a field on the dataset descriptor and `load()` enforces it: asking `load()` for a tier-1 dataset raises and names `fetch()` instead. Do not add a network call to a tier-0 path — CI runs `-m "not network"` and `tests/test_docs.py` fails the build if an executed docs cell would fetch.

### Registry-driven dispatch

`registry.py` holds two tables, and nearly every extension goes through one of them rather than through an `if` branch:

- `DATASETS` — name → `Dataset` descriptor (layout, tier, levels, licence, revisions, location count, store). Bundled descriptors are **discovered** by opening each `.h5` and reading its root attributes, so the stores are self-describing: adding a new contact source is dropping CSVs in `raw_data/` and re-running `build_hdf5.py`. The contact sources that are fetched rather than bundled (`prem2017`, `mistry2021`, in `fetched/` outside the wheel) are described by the manifest `data/fetched.json`, which `build_hdf5.py` writes with each store's pinned URL, SHA-256, locations and provenance.
- `LAYOUTS` — layout name → the shaper that turns a stored array into a dataframe (`matrix`, `crude`, `mortality`, `population`, `nodes`).

`load()` resolves the descriptor, picks the source for the revision, resolves the location scoped to that dataset, then hands off to the shaper with an `opts` dict carrying layout-specific arguments (`kind` for matrices, `level` for nodes). An argument a layout has no use for is **rejected, not ignored**. `register_dataset()`, `register_layout()` and `plotting.PLOTTERS` are the public hooks; a descriptor with a `loader` makes `load()` delegate entirely, which is how downstream code adds data this package doesn't ship.

Descriptor discovery is cached — call `registry.refresh()` if the files change inside a running process (e.g. a test that rebuilds a store).

### Import conventions

Follow Starsim's convention: **`from` imports live only in `__init__.py`**. Every other module does `import starsim_data as ssd` and reaches everything as `ssd.load`, `ssd.registry.datasets()`, so modules can refer to each other freely without cycles. The import order in `__init__.py` is load-bearing: `registry` must exist before `loaders` (which registers layouts) and `fetching` (which registers tier-1 datasets).

Importing the package must stay side-effect free — no directories created, no files opened, no warnings. `options` reads the environment at import but acts on it lazily; the cache dir is resolved and created only when something is written. The `[spatial]` imports are lazy for the same reason: `import starsim_data` works without geopandas, and only the spatial functions raise.

### Invariants that are enforced as data, not as memory

- **Provenance travels with the data.** `scripts/provenance.py` stamps source/URL/licence/citation/build details into each store at build time; `load()` and `fetch()` put the same record in `df.attrs['provenance']`. `tests/test_provenance.py` asserts the licences recorded in the stores match `NOTICE.md`.
- **GADM is never redistributed.** Its `ShapeSource` sets `redistributable=False`, `fetch_shapes()` leaves it out of the UNOCHA→geoBoundaries fallback chain, and `build_nodes.py` refuses any source with that flag. Keep the constraint on the descriptor rather than in a comment or a conditional.
- **Demographic stores are versioned by WPP revision**, as `demographics-<revision>.h5`. A new UN release is an additive rebuild, never an edit to data already in use.
- **Namibia's ISO-2 code is the string `NA`.** Any CSV read must pass `keep_default_na=False` or use the `csv` module, or pandas turns Namibia into a missing value. There is a regression test for it in `tests/test_locations.py`.
- **Location resolution is exact.** Fuzzy matching (`sc.suggest`) only builds the "did you mean" error message; it never resolves a name.

### Licensing

Code is MIT; each bundled dataset keeps its own upstream licence (GPL-3.0 for the Prem matrices, Apache-2.0 for `mistry2021`, CC BY 3.0 IGO for WPP). `NOTICE.md` is the operative attribution text and `licenses/` holds the full upstream texts. If you add or change a data source, update `NOTICE.md` — a test checks it against what the stores record.

## Documentation

Narrative pages are `.qmd` files in `docs/`, built by [great-docs](https://posit-dev.github.io/great-docs/). There is no navigation or API-reference config to maintain: the sidebar comes from each page's `guide-section` frontmatter and the reference is discovered from the public API. Rules `tests/test_docs.py` enforces:

- Every page needs `title` and a `guide-section` from `Getting started` / `The data` / `Internals`, and sections must stay **contiguous in filename order** — inserting a page in an earlier section means renumbering the later ones.
- Renumbering is safe: site URLs strip the numeric prefix (`docs/09-provenance.qmd` → `user-guide/provenance.html`), so cross-page links are written as bare `provenance.qmd`.
- Only the landing page (`01-getting-started.qmd`) prefixes links with `user-guide/`.
- Executed `{python}` cells must not fetch anything; write downloading examples as static ` ```python ` blocks.

`docs/08-architecture.qmd` is the long-form version of the Architecture section above, and stays in step with the code by executing against it.

### Keeping the docs in step

Docs are part of a change, not a follow-up to it. Before treating any change as done, check what it obliges you to update.

**When you add or remove a docs page:**

1. Give it `title` and a `guide-section`, then **renumber siblings so the sections stay contiguous** in filename order — a new `The data` page means bumping every `Internals` page. Use `git mv`; site URLs strip the numeric prefix, so no links break.
2. **Do not add navigation config to `great-docs.yml`.** A new page needs no entry there, by design — the sidebar is built from `guide-section` and the reference from the public API, so neither can fall out of step with the code. `test_docs.py::test_config_uses_native_navigation` fails if `sections` or a hand-written `reference.contents` shows up. Wanting to edit that file is usually a sign something else is wrong. The one real exception: introducing a *new* `guide-section` means adding it to `SECTIONS` in `tests/test_docs.py`, which defines both the allowed values and their order.
3. Link it from at least one sibling page — otherwise it is reachable only from the sidebar.
4. Update the hand-maintained places that count or list pages: the "N narrative pages" sentence in `CHANGELOG.md`, and the per-file table in `tests/README.md` when tests change. (That table is currently missing `test_docs.py`, `test_nodes.py` and `test_spatial.py` — prose duplicating a file listing goes stale exactly this way.)
5. Run `pytest tests/test_docs.py`, then `great-docs build` if Quarto is available. The tests catch frontmatter, dead cross-links and accidental network use; only a real build catches a cell that raises.

**When code changes:** the API reference regenerates itself, but prose does not. A new dataset, layout or source touches `docs/03-datasets.qmd` (schema), `docs/06-datasources.qmd` (coverage, licensing, limitations) and `NOTICE.md`; a new extension point touches `docs/08-architecture.qmd`. Docs cells execute against the package at build time, so a stale *example* fails docs CI — but a stale *sentence* will not, and nothing will catch it for you.

README links to the built site are `https://starsimhub.github.io/starsim_data/user-guide/<name>.html`.
