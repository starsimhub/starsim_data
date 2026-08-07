# Changelog

All notable changes to `starsim_data` are recorded here. Versions follow [semantic versioning](https://semver.org); the *data* is versioned too, so a change to a bundled dataset is a release, not an amendment.

## 0.4.0 (2026-08-07)

The spatial tier ([laser-init merge plan](plans/laser-init-merge.md) P2). Base install gains one bundled file and no new dependencies; full geometry and rasters are behind a new `[spatial]` extra.

### Added

- **The node table** (`ssd.load_nodes`), bundled. For every administrative unit at levels 0 and 1: `nodeid`, `location`, `iso3`, `level`, `name`, `pcode`, `dot_name`, `parent`, `lat`, `lon`, `area_km2`, `population`, `source`. 3,254 nodes across 184 countries in 1.4 MB, readable with no geospatial dependencies — which settles the question the plan left open: it bundles rather than shipping as a release asset. Built by `scripts/build_nodes.py` from UNOCHA COD-AB where it exists (the source of the p-codes, ~110 countries) and geoBoundaries CGAZ v6.0.0 elsewhere; the two disagree in places about how a country subdivides, so every row records which source it came from. `population` is national-only by design.
- **`ssd.distances()`** — the great-circle distance matrix between node centroids, which with `load_nodes()` gives a gravity model its `P_i`, `P_j` and `D_ij`. The gravity formulation itself stays in the model.
- **`ssd.fetch_shapes()`** — administrative boundaries with full geometry, from UNOCHA, geoBoundaries or GADM, normalized onto one schema and joining to the node table on `pcode`. `source=None` tries UNOCHA then geoBoundaries. **GADM is never reached automatically**: it is non-commercial only, so it must be named explicitly, and the constraint is enforced as data (`ShapeSource.redistributable`) rather than remembered — the node-table build refuses any source that sets it False.
- **`ssd.fetch_raster()`, `ssd.aggregate_raster()`, `ssd.fetch_nodes()`** — WorldPop 1 km gridded population, and summing it inside each administrative unit. This is the step that turns a boundary file into a metapopulation. `ssd.rescale_to_national()` reconciles WorldPop's modelled totals with UN WPP's (they differ by about 1.2% for Kenya 2020).
- **`ssd.choropleth()`**, and a `nodes` panel for `plot()` that draws centroids without needing any geospatial dependency.
- **`[spatial]` extra** (`geopandas`, `pyogrio`, `rastertoolkit`), imported lazily: `import starsim_data` works without them, and only the spatial functions raise if they are missing.
- **A documentation site**, built with [great-docs](https://posit-dev.github.io/great-docs/): nine narrative pages in `docs/` covering the tier model, the schema of every dataset, location resolution, the spatial tier, the source comparison, the internal architecture, provenance, and how the bundled files are generated — plus an API reference generated from the docstrings. Code examples are executed at build time, so the frames and figures shown are the package's actual output. Configuration is `great-docs.yml`, with `scripts/build_docs_theme.py` generating the sidebar navigation and footer so the site matches the rest of the Starsim documentation; `.github/workflows/docs.yml` builds and deploys it. NOTICE.md gains entries for UNOCHA, geoBoundaries, WorldPop and GADM.

### Changed

- `Dataset.level` becomes `Dataset.levels`, a tuple, since the node table spans two. `level` remains as a property giving the finest available.
- `parse_level()` now accepts up to level 5, not 4 — geoBoundaries and GADM both publish that deep, and the old cap made valid levels unreachable.
- Layout shapers take an options dict rather than a bare `kind`, so a layout can use whichever per-call arguments apply to it; `load()` gains `level=`, which it rejects for anything but the node table.

## 0.3.0 (2026-08-07)

Second tranche of the [laser-init merge plan](plans/laser-init-merge.md) (P1). No new packages are installed: everything here is built on sciris and the standard library.

### Added

- **`fetch()` — the data that is deliberately not bundled.** `load()` is still instant, offline and frozen; `fetch()` closes the three gaps the README has always named: annual resolution instead of decadal, complete life tables (`qx`, `lx`, `ex`, ...) instead of just `mx`, and other projection variants instead of Medium only. It reads the UN's public bulk CSVs — no API token, unlike the Data Portal — and caches them. `ssd.fetch('kenya', which='deaths', years=(2000, 2025))`, `ssd.fetch('kenya', which='life_table', years=2020)`, `ssd.fetch('kenya', which='births', variant='High')`. For the four series that are also bundled it returns exactly the schema `load()` returns, verified against the bundled data; `life_table` and `indicators` are fetch-only. See `ssd.list_fetchable()`.
- **A download cache**, with a provenance sidecar per file recording its URL, timestamp, size and SHA-256. `ssd.cache_dir()`, `ssd.cache_info()`, `ssd.cache_provenance()`, `ssd.clear_cache()`. The location defaults to a platform-appropriate directory and is overridable via `ssd.options.cache_dir` or `STARSIM_DATA_CACHE_DIR`.
- **`ssd.options`**, following Starsim's `ss.options` conventions, with `set()`, `reset()`, `help()` and a `context()` manager. Settings are read from the environment but acted on lazily: importing the package still creates no directories, opens no files and emits no warnings.
- **`plot()` — validation figures.** `ssd.plot('kenya')` draws a four-panel summary (age pyramid, crude birth rate, mortality curve, contact matrix); `ssd.plot('kenya', which='population')` draws one panel. The point is to catch the wrong country or the wrong units before the data reaches a simulation.
- **A dataset registry** (`ssd.registry`) holding a descriptor per dataset — layout, tier, admin level, license, revisions, location count — with public `register_dataset()` and `register_layout()` hooks. `ssd.list_datasets(detailed=True)` returns it as a dataframe, and `list_datasets(tier=0)` selects just the bundled data.
- **Tiers.** Datasets now declare whether they are bundled in the wheel (0), a downloaded release asset (1) or fetched from upstream (2). `load()` refuses anything above tier 0 and points at `fetch()`, so its "never touches the network" guarantee is now enforced by the code rather than by convention.

### Changed

- `load()` dispatches through the registry's layout table instead of an if-chain on `spec['layout']`, and finds its stores through descriptors instead of a filename glob. A new data family is now a shaper plus a registry entry.
- Internal imports follow Starsim's convention — `import starsim_data as ssd` — with `from` imports confined to `__init__.py`.
- `pandas` and `matplotlib` are now declared dependencies. Both were already installed as sciris dependencies; they are listed because the package imports them directly.

### Notes

- No CLI. Everything a CLI would have exposed — listing, loading, fetching, plotting, cache management, settings — is a library call, which is the interface a data package should have.

## 0.2.0 (2026-08-07)

First tranche of the [laser-init merge plan](plans/laser-init-merge.md) (P0).

### Added

- **Location resolution.** Locations can now be given as an ISO-2 or ISO-3 code, an official name, a translation, or a common abbreviation: `ssd.load('USA', ...)`, `ssd.load('KEN', ...)`, `ssd.load("Côte d'Ivoire", ...)` and `ssd.load('DRC', ...)` all work. Matching is exact against a table generated into `data/locations.csv`; fuzzy matching (via `sc.suggest`) is used only to suggest alternatives in the error message when a lookup fails, never to resolve one.
- `ssd.resolve()`, `ssd.location_info()` and `ssd.list_all_locations()` for working with the location table directly.
- `ssd.parse_level()`, accepting `'admin1'` / `'ADM2'` / `'3'` / `2`. Only level 0 has data today; this fixes the vocabulary before subnational data arrives.
- **Provenance.** Every bundled store now records its source, URL, license, citation and build details, written into the HDF5 at build time so it cannot be separated from the data. Read it with `ssd.provenance(which)`, or from `df.attrs['provenance']` on any loaded frame. Tests assert that the licenses recorded in the data match the ones asserted in `NOTICE.md`.
- **Revision-versioned demographics.** UN WPP data is now stored as `demographics-<revision>.h5`. `load()` uses the newest bundled revision by default; `load(..., revision=2024)` pins one, and `ssd.list_revisions()` lists them. A future WPP release becomes an additive rebuild rather than a silent change to data already in use.
- `iso3`, `official_name` and `aliases` columns in `data/locations.csv`, generated by the new `scripts/build_locations.py` from `pycountry` (a build-time dependency only).
- CI (`.github/workflows/tests.yml`), pytest markers (`network`, `slow`, `integration`), and this changelog. CI additionally rebuilds every store from `raw_data/` and re-runs the tests against the result, so the committed build artifacts cannot drift from their sources.

### Fixed

- **Namibia was silently missing from all four demographic series.** Its ISO-2 code is the string `NA`, which pandas' default `na_values` reads as NaN, so it was dropped from every ISO-2-keyed lookup — in `download_wpp.py` (so it was never downloaded at all), in `build_demographics.py`, and in anything else reading `locations.csv`. Every reader now disables NA coercion, the WPP data has been refetched, and the bundled demographics cover all 187 countries (previously 186). `build_demographics.py` additionally warns about any location in `locations.csv` that ends up with no data, and `test_namibia_has_demographic_data` guards against a regression. Contact matrices were never affected.

### Changed

- `starsim_data/data/demographics.h5` is replaced by `demographics-2024.h5`. Code calling `ssd.load(..., which='deaths')` is unaffected; anything reading the file path directly needs updating.
- `load()` results now carry `location`, `dataset` and `provenance` in `.attrs`.

### Notes

- `ss.Births(birth_rate=ssd.load(loc, which='births'))` previously raised `KeyError: 'Year'`, because this package emits UN-native `Time` while `ss.Births` defaulted to `Year`. Fixed upstream in Starsim (`ss.Deaths` and `ss.Pregnancy` already used `Time`); no workaround was added here.

## 0.1.0

Initial release: UN WPP demographics and `prem2017` / `prem2021` / `mistry2021` contact matrices, bundled as HDF5 and read with `load()`.
