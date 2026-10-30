# Changelog

All notable changes to `starsim_data` are recorded here. Versions follow [semantic versioning](https://semver.org); the *data* is versioned too, so a change to a bundled dataset is a release, not an amendment.

## Unreleased

- **The function says whose server it uses.** `ssd.fetch()` now gets only the stores this package publishes with its releases (`prem2017`, `mistry2021`, `mistry2021_us`, `population_us`), which are checked against a pinned SHA-256 and are the same for everyone on a version. Data from its original publisher has its own verb: `ssd.download('kenya', which='deaths', years=(2000, 2025))` for UN WPP, and `download_shapes()`, `download_nodes()` and `download_raster()` for boundaries and WorldPop, whose servers this package does not control. `list_downloadable()` lists what `download()` can get, and `list_fetchable()` now lists only the published stores.
- Existing code keeps working: `fetch()` of a UN WPP series, and `fetch_shapes()`, `fetch_nodes()` and `fetch_raster()`, warn that the data is not packaged and is being downloaded from an external source, then call the `download` function.
- `Dataset.function` gives the function that gets each dataset (`'load'`, `'fetch'` or `'download'`), and the errors that point elsewhere name the right one.

## Version 2.1.0 (2026-10-29)

- **Age-specific fertility rates.** `ssd.load('nigeria', which='fertility')` returns UN WPP 2024's fertility rates by 5-year age group of mother (`10–14` to `50–54`), as `[Time, AgeGrpStart, ASFR]`, in births per 1,000 women per year, for all 187 countries, bundled like `births` (decadal, 1950–2100, Medium variant). It is what `ss.Pregnancy` needs, where `births` (the crude rate) is what `ss.Births` needs. It adds about 0.1 MB to the download (0.65 MB installed).
- `ssd.fetch('nigeria', which='fertility')` gives the same every year, or for another variant, from the UN's `WPP2024_Fertility_by_Age5.csv.gz` (83 MB, once).
- `ssd.__version__` is the package's version; it said `0.4.0` in 2.0.0.
- `ssd.list_datasets(detailed=True)` has an `access` column, saying whether each dataset is **bundled** (inside the package), **fetched** (published with this package's releases and downloaded once) or **downloaded** (from its original publisher, such as the UN), in place of the `tier` column. `Dataset.access` gives the same.
- Each documentation page shows how much of it was written by a human and how much by AI.
- The documentation looks more like Starsim's (Raleway, its colors and headings), its API reference is one page per module, written by quartodoc as Starsim's is, and "Data tiers" is now [Bundled, fetched and downloaded data](https://starsimhub.github.io/starsim_data/user-guide/access.html).
- The documentation is built with Sciris' forks of great-docs and quartodoc (quartopydoc), installed with `pip install --group docs`, and its sources have moved to `docs/user-guide/`, with the configuration in `docs/great-docs.yml`.

## Version 2.0.0 (2026-10-22)

- **Contact matrices for 187 locations by default.** `ssd.load('kenya')` returns the contact matrices of Prem et al. 2021 (`prem2021`), and for the ten locations that study left out (Japan, Australia, Haiti and seven others) those of Prem et al. 2017 (`prem2017`). Pass `which='prem2021'` for that study alone.
- **A smaller package.** The other contact sources, `prem2017` and `mistry2021`, are downloaded the first time they are used, e.g. `ssd.fetch('france', which='mistry2021')`, rather than shipped with the package.
- **Subnational populations and borders, offline.** `ssd.load_nodes('kenya', level=1)` now gives the population of every state or province (from WorldPop, 2020), and `ssd.adjacency('kenya', level=1)` says which of them share a border.
- **Finer levels on request.** `ssd.fetch_nodes('kenya', level=2)` builds the same table (centroids, areas, populations and borders) at any level, e.g. Kenya's 290 sub-counties.
- **US states.** `ssd.fetch('United States:Massachusetts', which='mistry2021_us')` gives a state's contact matrices (Mistry et al. 2021), and `which='population_us'` its population by single year of age (US Census Bureau, 2023). A subnational unit is named `'<country>:<unit>'`, as in the node table.
- `fetch()` takes `kind=` for the contact matrices, and rejects arguments that do not apply.
- The fetched stores are downloaded from a GitHub release rather than from raw.githubusercontent.com, which rate-limits heavily.
- Requires Sciris 3.5.2 or later.

## Version 1.0.0 (2026-08-08)

Merged with the [laser-init](https://github.com/laser-base/laser-init) project with additional features for geospatial modeling, name resolution, etc.

### Resolution and provenance

- **Location resolution.** Locations can now be given as an ISO-2 or ISO-3 code, an official name, a translation, or a common abbreviation: `ssd.load('USA', ...)`, `ssd.load('KEN', ...)`, `ssd.load("Côte d'Ivoire", ...)` and `ssd.load('DRC', ...)` all work. Matching is exact against a table generated into `data/locations.csv`; fuzzy matching (via `sc.suggest`) is used only to suggest alternatives in the error message when a lookup fails, never to resolve one.
- `ssd.resolve()`, `ssd.location_info()` and `ssd.list_all_locations()` for working with the location table directly.
- `ssd.parse_level()`, accepting `'admin1'` / `'ADM2'` / `'3'` / `2`. Only level 0 has data today; this fixes the vocabulary before subnational data arrives.
- **Provenance.** Every bundled store now records its source, URL, license, citation and build details, written into the HDF5 at build time so it cannot be separated from the data. Read it with `ssd.provenance(which)`, or from `df.attrs['provenance']` on any loaded frame. Tests assert that the licenses recorded in the data match the ones asserted in `NOTICE.md`.
- **Revision-versioned demographics.** UN WPP data is now stored as `demographics-<revision>.h5`. `load()` uses the newest bundled revision by default; `load(..., revision=2024)` pins one, and `ssd.list_revisions()` lists them. A future WPP release becomes an additive rebuild rather than a silent change to data already in use.
- `iso3`, `official_name` and `aliases` columns in `data/locations.csv`, generated by the new `scripts/build_locations.py` from `pycountry` (a build-time dependency only).
- CI (`.github/workflows/tests.yml`), pytest markers (`network`, `slow`, `integration`), and this changelog. CI additionally rebuilds every store from `raw_data/` and re-runs the tests against the result, so the committed build artifacts cannot drift from their sources.

### Data loading

- **`fetch()` — the data that is deliberately not bundled.** `load()` is still instant, offline and frozen; `fetch()` closes the three gaps the README has always named: annual resolution instead of decadal, complete life tables (`qx`, `lx`, `ex`, ...) instead of just `mx`, and other projection variants instead of Medium only. It reads the UN's public bulk CSVs — no API token, unlike the Data Portal — and caches them. `ssd.fetch('kenya', which='deaths', years=(2000, 2025))`, `ssd.fetch('kenya', which='life_table', years=2020)`, `ssd.fetch('kenya', which='births', variant='High')`. For the four series that are also bundled it returns exactly the schema `load()` returns, verified against the bundled data; `life_table` and `indicators` are fetch-only. See `ssd.list_fetchable()`.
- **A download cache**, with a provenance sidecar per file recording its URL, timestamp, size and SHA-256. `ssd.cache_dir()`, `ssd.cache_info()`, `ssd.cache_provenance()`, `ssd.clear_cache()`. The location defaults to a platform-appropriate directory and is overridable via `ssd.options.cache_dir` or `STARSIM_DATA_CACHE_DIR`.
- **`ssd.options`**, following Starsim's `ss.options` conventions, with `set()`, `reset()`, `help()` and a `context()` manager. Settings are read from the environment but acted on lazily: importing the package still creates no directories, opens no files and emits no warnings.
- **`plot()` — validation figures.** `ssd.plot('kenya')` draws a four-panel summary (age pyramid, crude birth rate, mortality curve, contact matrix); `ssd.plot('kenya', which='population')` draws one panel. The point is to catch the wrong country or the wrong units before the data reaches a simulation.
- **A dataset registry** (`ssd.registry`) holding a descriptor per dataset — layout, tier, admin level, license, revisions, location count — with public `register_dataset()` and `register_layout()` hooks. `ssd.list_datasets(detailed=True)` returns it as a dataframe, and `list_datasets(tier=0)` selects just the bundled data.
- **Tiers.** Datasets now declare whether they are bundled in the wheel (0), a downloaded release asset (1) or fetched from upstream (2). `load()` refuses anything above tier 0 and points at `fetch()`, so its "never touches the network" guarantee is now enforced by the code rather than by convention.

### Nodes and distances

- **The node table** (`ssd.load_nodes`), bundled. For every administrative unit at levels 0 and 1: `nodeid`, `location`, `iso3`, `level`, `name`, `pcode`, `dot_name`, `parent`, `lat`, `lon`, `area_km2`, `population`, `source`. 3,254 nodes across 184 countries in 1.4 MB, readable with no geospatial dependencies — which settles the question the plan left open: it bundles rather than shipping as a release asset. Built by `scripts/build_nodes.py` from UNOCHA COD-AB where it exists (the source of the p-codes, ~110 countries) and geoBoundaries CGAZ v6.0.0 elsewhere; the two disagree in places about how a country subdivides, so every row records which source it came from. `population` is national-only by design.
- **`ssd.distances()`** — the great-circle distance matrix between node centroids, which with `load_nodes()` gives a gravity model its `P_i`, `P_j` and `D_ij`. The gravity formulation itself stays in the model.
- **`ssd.fetch_shapes()`** — administrative boundaries with full geometry, from UNOCHA, geoBoundaries or GADM, normalized onto one schema and joining to the node table on `pcode`. `source=None` tries UNOCHA then geoBoundaries. **GADM is never reached automatically**: it is non-commercial only, so it must be named explicitly, and the constraint is enforced as data (`ShapeSource.redistributable`) rather than remembered — the node-table build refuses any source that sets it False.
- **`ssd.fetch_raster()`, `ssd.aggregate_raster()`, `ssd.fetch_nodes()`** — WorldPop 1 km gridded population, and summing it inside each administrative unit. This is the step that turns a boundary file into a metapopulation. `ssd.rescale_to_national()` reconciles WorldPop's modeled totals with UN WPP's (they differ by about 1.2% for Kenya 2020).
- **`ssd.choropleth()`**, and a `nodes` panel for `plot()` that draws centroids without needing any geospatial dependency.
- **`[spatial]` extra** (`geopandas`, `pyogrio`, `rastertoolkit`), imported lazily: `import starsim_data` works without them, and only the spatial functions raise if they are missing.
- **A documentation site**, built with [great-docs](https://posit-dev.github.io/great-docs/): narrative pages in `docs/` covering the tier model, the schema of every dataset, location resolution, the spatial tier, the source comparison, how this package relates to [epydemix-data](https://github.com/epistorm/epydemix-data), [laser-init](https://github.com/laser-base/laser-init) and the other projects distributing the same data, the internal architecture, provenance, how the bundled files are generated, and this changelog — plus an API reference generated from the docstrings. Code examples are executed at build time, so the frames and figures shown are the package's actual output. Both the sidebar and the API reference are built by great-docs itself — from the pages' `guide-section` frontmatter and from the public API — so neither can fall out of step with the code; the only hand-written styling is three overrides great-docs has no setting for (figure scaling, navbar centering, and the Starsim footer); `.github/workflows/docs.yml` builds and deploys it. NOTICE.md gains entries for UNOCHA, geoBoundaries, WorldPop and GADM.


## Version 0.1.0

Initial release: UN WPP demographics and `prem2017` / `prem2021` / `mistry2021` contact matrices, bundled as HDF5 and read with `load()`.
