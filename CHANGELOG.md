# Changelog

What's new in each version of `starsim_data`. The data is versioned along with the code: any change to the included data is a new version, so a given version always gives the same data.

## Version 2.2.0 (2026-10-20)

- **The function name says where data comes from.** `ssd.fetch()` now gets only the data this package publishes but doesn't include to save space (`prem2017`, `mistry2021`, `mistry2021_us` and `population_us`), which is the same for everyone on a version. Data that comes straight from the organization that publishes it has its own function, `ssd.download()`, e.g. `ssd.download('kenya', which='deaths', years=(2000, 2025))` for annual UN data. `download_shapes()`, `download_nodes()` and `download_raster()` do the same for boundaries and WorldPop. These servers are outside this package's control, so they may be slow or unavailable.
- Existing code keeps working: `fetch()` of UN data, and `fetch_shapes()`, `fetch_nodes()` and `fetch_raster()`, still work, with a warning that the data is coming from an external source.

## Version 2.1.0 (2026-10-29)

- **Age-specific fertility rates.** `ssd.load('nigeria', which='fertility')` gives the UN's fertility rates by 5-year age group of mother, in births per 1,000 women per year, for all 187 countries. This is what `ss.Pregnancy` needs, just as `births` (the crude birth rate) is what `ss.Births` needs. `ssd.fetch('nigeria', which='fertility')` gives the same for every year, or for another UN projection.
- `ssd.list_datasets(detailed=True)` says whether each dataset is **bundled** (included in the package), **fetched** (published by this package and downloaded the first time it's used) or **downloaded** (from the organization that publishes it).
- The documentation looks more like Starsim's, and each page shows how much of it was written by a human and how much by AI.
- `ssd.__version__` now gives the right version.

## Version 2.0.0 (2026-10-22)

- **Contact matrices for 187 countries by default.** `ssd.load('kenya')` gives the contact matrices of Prem et al. 2021, and for the ten countries that study left out (such as Japan and Australia), those of Prem et al. 2017. Use `which='prem2021'` for the 2021 study alone.
- **A smaller package.** The other contact matrices, `prem2017` and `mistry2021`, are downloaded the first time you use them, e.g. `ssd.fetch('france', which='mistry2021')`.
- **Subnational populations and borders, offline.** `ssd.load_nodes('kenya', level=1)` gives the population of every state or province (from WorldPop, for 2020), and `ssd.adjacency('kenya', level=1)` says which of them share a border.
- **Finer levels on request.** `ssd.fetch_nodes('kenya', level=2)` gives the same information for districts, e.g. Kenya's 290 sub-counties.
- **US states.** `ssd.fetch('United States:Massachusetts', which='mistry2021_us')` gives a state's contact matrices (Mistry et al. 2021), and `which='population_us'` its population by single year of age (US Census Bureau, 2023).
- Downloads are more reliable.
- Requires Sciris 3.5.2 or later.

## Version 1.0.0 (2026-08-08)

Merged with the [laser-init](https://github.com/laser-base/laser-init) project, adding geography for spatial models.

### Finding data

- **Countries by any name.** `'USA'`, `'KEN'`, `"Côte d'Ivoire"`, `'DRC'` and official names, abbreviations and translations all work. A name that isn't recognized gives an error with suggestions, never a guess. `ssd.resolve()`, `ssd.location_info()` and `ssd.list_all_locations()` show how names are matched.
- **Citations travel with the data.** `ssd.provenance(which)` gives each dataset's source, license and citation, and every dataframe carries the same in `df.attrs['provenance']`.
- **UN data by revision.** `load()` uses the newest UN WPP revision included; `revision=` picks another, and `ssd.list_revisions()` lists them. A new UN release will be added alongside, rather than changing data already in use.

### More data

- **`fetch()`**, for UN data that isn't included: annual rather than every 10 years, full life tables (`qx`, `lx`, `ex`, …) and other projections (High, Low, …), e.g. `ssd.fetch('kenya', which='life_table', years=2020)`. No UN account is needed. Downloads are saved on your computer and reused; `ssd.cache_info()` and `ssd.clear_cache()` manage them.
- **`ssd.plot()`**, to check data by eye: `ssd.plot('kenya')` draws the age pyramid, birth rate, mortality curve and contact matrix.
- **`ssd.options`**, for settings such as where downloads are saved and how much is printed.

### Geography

- **The node table.** `ssd.load_nodes('kenya', level=1)` gives every state or province of 184 countries, with its location, area, place in the hierarchy and the `pcode` that subnational health data uses. It is included in the package, and needs no extra software.
- **`ssd.distances()`**, the distances between them, which together with populations is what a gravity model needs.
- **Boundaries and population grids**, with the optional `[spatial]` packages: `ssd.fetch_shapes()` for boundaries from UNOCHA, geoBoundaries or GADM (only on request, as it is for non-commercial use only), `ssd.fetch_nodes()` for populations from WorldPop, and `ssd.choropleth()` for maps. `ssd.rescale_to_national()` makes WorldPop's populations add up to the UN's national total.
- **A documentation website**, covering every dataset, where it comes from, and how this package relates to others.

## Version 0.1.0

First release: UN WPP demographics and contact matrices (`prem2017`, `prem2021` and `mistry2021`), read with `load()`.
