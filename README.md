# Starsim Data

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/starsimhub/starsim_data/blob/main/LICENSE)

National-level **demographic data** and **contact matrices** for disease modeling with [Starsim](https://starsim.org), bundled as compact HDF5 and loaded with a single function. 

Example usage:

```python
import starsim_data as ssd

ssd.list_datasets()                              # what's available
ssd.load('kenya', which='deaths')                # UN WPP mortality rates (tidy DataFrame)
ssd.load('kenya', kind='home')                   # a contact matrix (square DataFrame)
ssd.provenance('prem')                           # where it came from, and its license
ssd.plot('kenya')                                # eyeball it before it goes into a model
ssd.fetch('kenya', which='deaths', years=(2000, 2025))  # annual data, downloaded on demand
```

Locations can be named however you like: `'Kenya'`, `'kenya'`, `'KE'`, `'KEN'` and `'Republic of Kenya'` are the same country, as are `'USA'`, `'US'`, `'united states'` and `'United States of America'`. ISO-2/ISO-3 codes, official names, common abbreviations (`UK`, `DRC`) and French/Spanish/Portuguese names all resolve; accents, case and punctuation are ignored, so `"Côte d'Ivoire"` and `'cote divoire'` both work. A name that doesn't match raises, with suggestions — it is never resolved to the nearest guess. Use `ssd.list_locations(which)` for the countries in a given dataset, `ssd.list_all_locations()` for every known location, and `ssd.resolve()`/`ssd.location_info()` to inspect the mapping.

**Documentation:** <https://starsimhub.github.io/starsim_data>

## Installation

```bash
pip install starsim_data # or, from a clone: pip install -e .
```

---

# What's included

There are two families of data. `ssd.load()` returns a [Sciris](https://sciris.org) (`pandas`-compatible) dataframe whose shape depends on the dataset.

## 1. Demographics (UN World Population Prospects 2024)

Sourced from the [UN WPP 2024](https://population.un.org/wpp/), Medium variant, for all 187 countries every 10 years from 1950 to 2100 (16 time points). Grouped in `demographics-2024.h5`, exposed as five datasets whose `load()` result is a [Starsim](https://starsim.org)-ready dataframe with UN-native column names:

| `which=` | What it is | Age resolution | Columns returned |
|---|---|---|---|
| `births` | Crude birth rate (per 1,000) | none (national) | `[Time, CBR]` |
| `deaths` | Age/sex mortality rate `m(x)` | 5-year abridged (`0, 1–4, 5–9, …, 100+`) | `[Time, Sex, AgeGrpStart, mx]` |
| `migration` | Crude net-migration rate (per 1,000) | none (national) | `[Time, CNMR]` |
| `population` | Population counts (absolute persons) | 5-year (`0–4, 5–9, …, 100+`) | `[Time, Sex, AgeGrp, Value]` |
| `fertility` | Age-specific fertility rate (births per 1,000 women) | 5-year age of mother (`10–14, …, 50–54`) | `[Time, AgeGrpStart, ASFR]` |

These drop straight into Starsim: `deaths` matches `ss.Deaths`'s expected columns, `births` feeds `ss.Births`, `fertility` feeds `ss.Pregnancy`, and `population` gives age–sex pyramids for initialization.

**Not bundled:**

- ⬇️ Annual resolution — the bundled store has every 10th year (1950, 1960, …, 2100). Use [`fetch()`](#data-that-isnt-bundled) for annual.
- ⬇️ Life tables (`qx`, `lx`, `ex`, …) and the other WPP indicators (CDR, TFR, LEx, IMR, …) — available via [`fetch()`](#data-that-isnt-bundled).
- ⬇️ Non-Medium projection variants (High, Low, Constant fertility, …) — available via [`fetch()`](#data-that-isnt-bundled), except for life tables, which the UN publishes for Medium only.
- ❌ Subnational demographics (states, provinces, counties).
- ❌ Age-specific migration (crude rate only) — the UN provides no age breakdown for it.
- ❌ "Both sexes"/"Total" rows: Female + Male only.

Demographic data is versioned by UN WPP revision. `load()` reads the newest bundled revision; pass `revision=` to pin an older one, and see `ssd.list_revisions()` for what's available. A new WPP release therefore adds a store rather than changing data already in use.

## 2. Contact matrices

*Note: These data were adapted from the excellent [Epydemix](https://github.com/epistorm/epydemix-data) project*

Age-structured contact rates — the average number of contacts between age groups — across five settings (`all`, `home`, `work`, `school`, `community`), selected with the `kind=` argument. `load()` returns a square dataframe whose rows and columns are indexed by the start age of each bin (e.g. `0, 5, …, 75`), so you can select by age with `M.loc[25, 30]`. Data included are a trimmed subset of [epydemix-data](https://github.com/epistorm/epydemix-data):

| `which=` | Bundled | Matrix | Age groups | Countries | Source study |
|---|---|---|---|---|---|
| `prem` | ✅ (the default) | 16×16 | 5-year (`0–4, …, 75+`) | 187 | `prem2021`, and `prem2017` for the ten locations it lacks |
| `prem2021` | ✅ | 16×16 | 5-year (`0–4, …, 75+`) | 177 | [Prem et al. 2021](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009098) |
| `prem2017` | ⬇️ `fetch()` | 16×16 | 5-year (`0–4, …, 75+`) | 152 | [Prem et al. 2017](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005697) |
| `mistry2021` | ⬇️ `fetch()` | 85×85 | single-year (`0–84`, last is `84+`) | 36 | [Mistry et al. 2021](https://www.nature.com/articles/s41467-020-20544-y) |
| `mistry2021_us` | ⬇️ `fetch()` | 85×85 | single-year (`0–84`, last is `84+`) | 51 US states (with DC) | [Mistry et al. 2021](https://www.nature.com/articles/s41467-020-20544-y) |

The default uses `prem2021`, the authors' own update of `prem2017`, built from more contact surveys and newer demographic data; for the ten locations it dropped (such as Japan and Australia), it uses `prem2017`. The full `prem2017` (e.g. to reproduce earlier work) and `mistry2021` (for single years of age) are downloaded the first time they are used, about 3 MB each:

```python
ssd.fetch('japan', which='prem2017', kind='home')
ssd.fetch('france', which='mistry2021')
```

Not every country has every source; use `ssd.list_locations('prem2021')` etc. to check (this works for the fetched sources too, without downloading them). 

For the US states, `mistry2021_us` has the same study's matrices, and `population_us` each state's population by single year of age (US Census Bureau, 2023), to match. A state is named with its country, separated by a colon, as in the node table's `dot_name`:

```python
ssd.fetch('United States:Massachusetts', which='mistry2021_us', kind='school')
ssd.fetch('USA:massachusetts', which='population_us')
```

*Note:* `epydemix` has subnational contact matrices for other countries (and US counties) that are not included here.

---

## Data that isn't bundled

`load()` never touches the network: everything it reads is inside the wheel, which is what makes it instant, usable offline and reproducible from a pinned version. Data too big for that is reached through a different verb, so the cost is visible at the call site.

`ssd.fetch()` downloads the UN's public bulk CSVs (no API token needed) and filters them, returning the same schema `load()` does. It also downloads the contact sources that are not bundled (above).

```python
ssd.fetch('kenya', which='deaths', years=(2000, 2025))  # annual mx, not decadal
ssd.fetch('kenya', which='life_table', years=2020)      # qx, lx, ex, ... with a glossary in .attrs
ssd.fetch('kenya', which='births', variant='High')      # a different projection variant
ssd.fetch('kenya', which='indicators', years=2020)      # CDR, TFR, LEx, IMR and ~50 more
ssd.list_fetchable()                                    # what fetch() can get
```

`years=` takes a single year, a `(start, end)` tuple as an inclusive range, or an explicit list. The downloads are large — 17 MB for the indicators, 145 MB per half of the life table — so they are cached and reused:

```python
ssd.cache_dir()          # where downloads go (override with ssd.options.cache_dir
                         # or the STARSIM_DATA_CACHE_DIR environment variable)
ssd.cache_info()         # what's cached, from where, and when it was fetched
ssd.clear_cache()        # or clear_cache('wpp/*')
```

Every cached file records where and when it was downloaded, and `fetch()` results carry the same in `.attrs['provenance']`.

## Plotting

`ssd.plot(location)` draws a four-panel check — age pyramid, crude birth rate, mortality curve and contact matrix — and `ssd.plot(location, which=...)` draws just one. The point is to notice a wrong country or a units error before it reaches a simulation, not to make publication figures:

```python
ssd.plot('kenya')                              # everything available for Kenya
ssd.plot('kenya', which='population')          # just the age pyramid
ssd.plot('kenya', which='deaths', year=2050)   # a projected mortality curve
```

It returns the matplotlib figure, so styling and saving are up to you.

## Settings

```python
ssd.options.help()                     # what can be set, and what it currently is
ssd.options(verbose=False)             # quieten downloads
ssd.options.cache_dir = '/fast/scratch' # or set STARSIM_DATA_CACHE_DIR
with ssd.options.context(verbose=False):
    ...                                # temporarily
```

Settings are read from the environment but acted on lazily, so importing the package creates no directories and opens no files.

---

## Geographies

Demographics and contact matrices are national (level 0): 187 countries, every one with all five demographic series, and contact-matrix coverage varying by source (36–177). Canonical keys use `_` for spaces (e.g. `United_States`, `Sierra_Leone`), but you can pass any recognized name, code or alias — see the resolution rules above. The bundled `locations.csv` lists each country's ISO 3166-1 alpha-2 and alpha-3 codes, official name, aliases and available contact sources; `ssd.location_info(location)` returns a row of it.

### The node table

Subnational geography is bundled too, as a **node table**: for each administrative unit, where it is, how big it is, how many people live there, how it fits in the hierarchy, and which units it borders. That is most of what a metapopulation model needs, it is a couple of MB for the whole world, and it reads with no geospatial dependencies:

```python
ssd.load_nodes('kenya')                # 1 row: the country, with its UN WPP population
ssd.load_nodes('kenya', level=1)       # 47 counties: centroids, areas, populations, p-codes
ssd.distances('kenya', level=1)        # the 47x47 great-circle distance matrix, in km
ssd.adjacency('kenya', level=1)        # which counties share a border
ssd.plot('kenya', which='nodes', level=1)
```

Columns are `nodeid`, `location`, `iso3`, `level`, `name`, `pcode`, `dot_name`, `parent`, `lat`, `lon`, `area_km2`, `population` and `source`. Two are worth knowing about: **`pcode`** is the join key — for most countries it is the humanitarian p-code that subnational health data is keyed on — and **`dot_name`** is the readable hierarchical path (`Kenya:Baringo`), whose first component is always a location `load()` accepts.

Levels 0 and 1 are covered for 184 countries, built from UNOCHA COD-AB where it exists (~110 countries, and the source of the p-codes) and geoBoundaries CGAZ v6.0.0 elsewhere. The two disagree in places about how a country subdivides, so every row records which source it came from. Hong Kong, Macao and Puerto Rico have no boundaries in either source and are absent. `population` is UN WPP at level 0 and, at level 1, WorldPop's 2020 1 km raster summed within each unit when the table is built; other years and finer levels (`fetch_nodes('kenya', level=2)`) are a download, and live in the spatial extra below.

`ssd.parse_level()` accepts `'admin1'`, `'ADM2'`, `'3'` or a bare integer, up to 5.

### Boundaries, rasters and maps: the `[spatial]` extra

Actual polygons are far too big for a wheel, so they are fetched and cached, and they need the optional geospatial stack:

```bash
pip install starsim_data[spatial]
```

```python
ssd.list_shape_sources()                       # UNOCHA / geoBoundaries / GADM, and their terms
gdf = ssd.fetch_shapes('kenya', level=2)       # 290 sub-counties, with geometry
nodes = ssd.fetch_nodes('kenya', level=1)      # the node table, population filled from WorldPop
ssd.choropleth('kenya', level=1)               # a filled map
```

`fetch_shapes()` tries UNOCHA then geoBoundaries. **GADM is never tried automatically**: it is licensed for non-commercial use only, so it has to be asked for by name (`source='gadm'`), and nothing derived from it is ever bundled or redistributed. Shapes join to the node table on `pcode` and `dot_name`.

`fetch_nodes()` sums a WorldPop 1 km raster inside each unit. WorldPop's constrained estimates are modeled rather than counted and will not equal the UN WPP national total — about 1.2% low for Kenya in 2020 — so if your model needs them to agree, `ssd.rescale_to_national(nodes)` makes that choice explicit.

Together, `load_nodes()` and `distances()` are the inputs a gravity model needs (`P_i`, `P_j`, `D_ij`); the gravity formulation itself belongs in the model, not in a data package.

[Data sources](https://starsimhub.github.io/starsim_data/user-guide/datasources.html) compares every source in detail — coverage, admin depth, update cadence, licensing and what each is suited to.

## Related projects

Two projects shaped this one. [epydemix-data](https://github.com/epistorm/epydemix-data) — the data repository behind [epydemix](https://github.com/epistorm/epydemix) — is where the bundled contact matrices come from, along with the idea of a single manifest listing every location and the sources available for it. [laser-init](https://github.com/laser-base/laser-init), which bootstraps spatial models for [LASER](https://github.com/laser-base/laser-generic), is where the treatment of spatial data comes from: the three boundary sources and the reasons for preferring one over another, WorldPop as the population raster, and aggregating that raster inside administrative polygons to get a population per node.

The differences are mostly about delivery. epydemix-data resolves over the network from GitHub and covers 3,500+ regions including subnational contact matrices; this bundles national matrices in the wheel and adds the full UN WPP demographic series and a node table. laser-init is a CLI that downloads everything and writes out a runnable model; this is a library that returns dataframes and generates no model code — `load_nodes()` and `distances()` give a gravity model its inputs, but the gravity formulation belongs in the model. [Related projects](https://starsimhub.github.io/starsim_data/user-guide/related-projects.html) covers this in full, and compares both with the other ways of getting the same data.

## Citing

When you use these data, cite the underlying sources: the [UN World Population Prospects 2024](https://population.un.org/wpp/) for demographics, and the relevant contact-matrix study (Prem 2017, Prem 2021, and/or Mistry 2021) for each source you use. See [NOTICE.md](https://github.com/starsimhub/starsim_data/blob/main/NOTICE.md) for full attributions.

Each dataset also carries its attribution as data. `ssd.provenance(which)` returns the source, URL, license, citation and build details for a dataset, and every frame from `load()` has the same in `df.attrs['provenance']` — so the citation travels with the data rather than needing to be looked up:

```python
ssd.provenance('mistry2021').citation   # 'Mistry D, Litvinova M, ...'
ssd.provenance('deaths').license        # 'CC BY 3.0 IGO'
```

## Documentation

The full documentation is at <https://starsimhub.github.io/starsim_data>. The narrative pages are `.qmd` sources in [`docs/user-guide/`](docs/user-guide/), ordered by their filename prefix and grouped in the sidebar by their `guide-section` frontmatter; the API reference is written by quartopydoc, one page per module. It is built with [Sciris' fork of great-docs](https://github.com/sciris/great-docs) and [quartopydoc](https://pypi.org/project/quartopydoc/), which the `docs` dependency group installs. To build it locally you also need [Quarto](https://quarto.org/docs/get-started/):

```bash
pip install -e ".[dev]" --group docs
great-docs build      # -> docs/_site/
docs/render           # the same, rendering pages in parallel
great-docs preview    # live reload on http://localhost:3000
```

Adding a page means dropping a `.qmd` file in `docs/user-guide/` with a `title` and a `guide-section` — there is no navigation configuration to update (a new module, though, needs adding to the `quartodoc:` sections in `docs/great-docs.yml`). [`docs/user-guide/assets/starsim-theme.html`](docs/user-guide/assets/starsim-theme.html) holds the style overrides that make the site look like the Starsim docs (Raleway, the navbar, the sidebar, figure scaling, the authorship badge, and the Starsim footer).

## Building from source

The bundled `.h5` files are generated from the human-readable sources in [`raw_data/`](raw_data/) by the scripts in [`scripts/`](scripts/). See those folders' READMEs to regenerate or update the data. [CONTRIBUTING.md](CONTRIBUTING.md) has the steps for changing the data and making a release.

## License

The repository's code, packaging, and curation are licensed under the [MIT License](https://github.com/starsimhub/starsim_data/blob/main/LICENSE).

The bundled data files are third-party datasets under their own upstream licenses — the UN WPP data under its [terms of use](https://population.un.org/wpp/), and the contact matrices under **Apache-2.0** (`mistry2021`) and **GPL-3.0** (`prem2017`/`prem2021`) — not under MIT. Full upstream license texts are in [`licenses/`](https://github.com/starsimhub/starsim_data/blob/main/licenses), and [NOTICE.md](https://github.com/starsimhub/starsim_data/blob/main/NOTICE.md) has the per-source details and required attributions.
