# Starsim Data

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/starsimhub/starsim_data/blob/main/LICENSE)

This package provides demographic data, contact matrices, and administrative geography for [Starsim](https://starsim.org) (although it can of course be used for other applications as well). Commonly used data are available offline, while more detailed data are downloaded and cached. 

```python
import starsim_data as ssd

ssd.list_datasets()                    # What's available
ssd.load('kenya', which='deaths')      # UN mortality rates by age and sex
ssd.load('kenya', which='contacts')    # A contact matrix
ssd.load_nodes('kenya', level=1)       # Kenya's 47 counties: locations, areas, populations
ssd.provenance('prem')                 # Where the data came from, and how to cite it
ssd.plot('kenya')                      # See what the data look like before
```

Location naming is flexible: `'Kenya'`, `'kenya'`, `'KE'`, `'KEN'` and `'Republic of Kenya'` all work, as do common abbreviations (`'USA'`, `'UK'`, `'DRC'`) and names with or without accents (`"Côte d'Ivoire"`, `'cote divoire'`).

**Documentation:** <https://starsim.org/starsim_data>

## Installation

*Note: `starsim_data` is installed as part of Starsim, so typically you don't need to install it separately.*

```bash
pip install starsim_data # Standard usage
pip install starsim_data[spatial] # With support for subnational maps and geospatial shape boundaries
```

---

## What's included

`ssd.load()` returns a dataframe of the requested data.

### Demographics (UN World Population Prospects 2024)

From the [UN World Population Prospects 2024](https://population.un.org/wpp/) (WPP), for 187 countries, every 10 years from 1950 to 2100, using the UN's main (Medium) projection:

| `which=` | What it is | Age groups | Columns |
|---|---|---|---|
| `births` | Crude birth rate (per 1,000) | — | `Time, CBR` |
| `deaths` | Mortality rate by age and sex | 5-year (`0, 1–4, 5–9, …, 100+`) | `Time, Sex, AgeGrpStart, mx` |
| `migration` | Crude net migration rate (per 1,000) | — | `Time, CNMR` |
| `population` | Population by age and sex | 5-year (`0–4, …, 100+`) | `Time, Sex, AgeGrp, Value` |
| `fertility` | Age-specific fertility rate (per 1,000 women) | 5-year age of mother (`10–14, …, 50–54`) | `Time, AgeGrpStart, ASFR` |

These go straight into Starsim: `deaths` into `ss.Deaths`, `births` into `ss.Births`, `fertility` into `ss.Pregnancy`, and `population` gives the starting age structure.

Annual data, full life tables, other UN indicators and other projections (High, Low, …) aren't included, but can be downloaded from the UN (see [below](#data-that-isnt-included)). There is no subnational demographic data, and migration is a crude rate only, as the UN publishes it.

### Contact matrices

The average number of daily contacts between age groups, for five settings (`all`, `home`, `work`, `school`, `community`), chosen with `kind=`. Rows and columns are labeled by the youngest age in each group, so `M.loc[25, 30]` is contacts between 25–29 and 30–34 year olds. These were adapted from the excellent [epydemix-data](https://github.com/epistorm/epydemix-data) project.

| `which=` | Included | Age groups | Countries | Study |
|---|---|---|---|---|
| `contacts` (default) | ✅ | 5-year (`0–4, …, 75+`) | 187 | `prem2021`, plus `prem2017` for the ten countries it lacks |
| `prem2021` | ✅ | 5-year | 177 | [Prem et al. 2021](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009098) |
| `prem2017` | ⬇️ `fetch()` | 5-year | 152 | [Prem et al. 2017](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005697) |
| `mistry2021` | ⬇️ `fetch()` | single year (`0–84+`) | 36 | [Mistry et al. 2021](https://www.nature.com/articles/s41467-020-20544-y) |
| `mistry2021_us` | ⬇️ `fetch()` | single year (`0–84+`) | 50 US states and DC | [Mistry et al. 2021](https://www.nature.com/articles/s41467-020-20544-y) |

The default, `prem2021`, is the authors' update of `prem2017`, using more surveys and newer data; for the ten countries it dropped (such as Japan and Australia), the default falls back to `prem2017`. The fetched sources are a few MB each, and are downloaded the first time you use them:

```python
ssd.fetch('japan', which='prem2017', kind='home')
ssd.fetch('france', which='mistry2021')                                # single years of age
ssd.fetch('United States:Massachusetts', which='mistry2021_us')        # a US state
ssd.fetch('United States:Massachusetts', which='population_us')        # its population by single year of age
```

Not every country is in every source. You can use e.g. `ssd.list_locations('mistry2021')` to lists which ones are.

### Geography

For spatial models, the **node table** describes each country and its states or provinces, for 184 countries: basic geography, how many people live there, and which others it borders. It is included in the package and needs no extra software:

```python
ssd.load_nodes('kenya', level=1)       # 47 counties: name, latitude/longitude, area, population
ssd.distances('kenya', level=1)        # distances between them, in km
ssd.adjacency('kenya', level=1)        # which counties share a border
```

Populations are the UN's for countries and [WorldPop](https://www.worldpop.org)'s 2020 estimates for states and provinces. Each unit has a `pcode`, the code that most subnational health data uses for it, so you can join your own data on. Together, populations and distances are what a gravity model of travel between places needs.

Maps, finer levels (districts, sub-counties) and other years need the optional geospatial packages, and are downloaded on demand:

```bash
pip install starsim_data[spatial]
```

```python
ssd.download_shapes('kenya', level=2)   # boundaries of Kenya's 290 sub-counties
ssd.download_nodes('kenya', level=2)    # the node table for them, with WorldPop populations
ssd.choropleth('kenya', level=1)        # a map, colored by population
```

Boundaries come from [UNOCHA](https://data.humdata.org/dataset/?dataseries_name=COD+-+Subnational+Administrative+Boundaries) or [geoBoundaries](https://www.geoboundaries.org). [GADM](https://gadm.org) is also available, but only if you ask for it (`source='gadm'`), because its license allows non-commercial use only.

---

## Data that isn't included

`load()` uses data bundled in the package. For data that isn't included, there are two "tiers" of download:

- **`fetch()`** downloads data that this package stores on GitHub as a release asset, but doesn't bundle with the install for space reasons. These are the contact matrices above, plus US state population sizes.
- **`download()`** downloads data directly from the original source, such as the UN. These servers are outside this package's control, so they may be slow, change their data, or be unavailable. `download_shapes()`, `download_nodes()` and `download_raster()` do the same for boundaries and WorldPop.

```python
ssd.download('kenya', which='deaths', years=(2000, 2025))   # annual rather than every 10 years
ssd.download('kenya', which='life_table', years=2020)       # the full life table: qx, lx, ex, ...
ssd.download('kenya', which='births', variant='High')       # the UN's High projection
ssd.download('kenya', which='indicators', years=2020)       # TFR, life expectancy, IMR and ~50 more
```

The UN's files are large (up to a few hundred MB), so everything downloaded is cached; `ssd.cache_info()` shows what has been saved, and `ssd.clear_cache()` deletes it.

## Checking the data

`ssd.plot('kenya')` draws the age pyramid, birth rate, mortality curve and contact matrix for a country, and `ssd.plot('kenya', which='deaths', year=2050)` draws just one. It's meant to catch the wrong country or the wrong units before they reach a simulation, not to make publication figures.

## Citing

Please cite the sources of the data you use: the [UN World Population Prospects 2024](https://population.un.org/wpp/) for demographics, the contact-matrix study for each source you use, and WorldPop and the boundary source for geography. `ssd.provenance()` gives the citation and license for each dataset, and every dataframe carries the same in `df.attrs['provenance']`:

```python
ssd.provenance('mistry2021').citation   # 'Mistry D, Litvinova M, ...'
ssd.provenance('deaths').license        # 'CC BY 3.0 IGO'
```

[NOTICE.md](https://github.com/starsimhub/starsim_data/blob/main/NOTICE.md) has the full attributions.

## Related projects

This package builds on two others: [epydemix-data](https://github.com/epistorm/epydemix-data), where the contact matrices come from, and [laser-init](https://github.com/laser-base/laser-init), which sets up spatial models for [LASER](https://github.com/laser-base/laser-generic) and is where the approach to boundaries and populations comes from. See [Related projects](https://starsimhub.github.io/starsim_data/user-guide/related-projects.html) for more information.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers changing the code or the data, building the documentation, and making a release.

## License

The code is licensed under the [MIT License](https://github.com/starsimhub/starsim_data/blob/main/LICENSE). The data itself is licened under several different licenses. The UN WPP data is under [CC BY 3.0 IGO](https://population.un.org/wpp/), the contact matrices under GPL-3.0 (`prem2017`, `prem2021`) and Apache-2.0 (`mistry2021`), and the node table under CC BY 3.0 IGO (UNOCHA) and CC BY 4.0 (geoBoundaries, WorldPop). See [NOTICE.md](https://github.com/starsimhub/starsim_data/blob/main/NOTICE.md) and [`licenses/`](https://github.com/starsimhub/starsim_data/blob/main/licenses) for details.

## AI disclosure

Many tokens (mainly from Claude Opus 5.5) were harmed in the making of this repo. We believe in transparency around AI use. On most pages you will see a small marker like "🧠5% 🤖95%". This means that humans wrote 5% of the content, and AI wrote the other 95% (hover for details). We know reading AI-generated text can get tiring, so our long-term goal is to replace as much of it as possible.
