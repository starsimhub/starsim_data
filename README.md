# Starsim Data

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

National-level **demographic data** and **contact matrices** for disease modeling with [Starsim](https://starsim.org), bundled as compact HDF5 and loaded with a single function. 

Example usage:

```python
import starsim_data as ssd

ssd.list_datasets()                              # what's available
ssd.load('kenya', which='deaths')                # UN WPP mortality rates (tidy DataFrame)
ssd.load('kenya', which='prem2017', kind='home') # a contact matrix (square DataFrame)
ssd.provenance('prem2017')                       # where it came from, and its license
```

Locations can be named however you like: `'Kenya'`, `'kenya'`, `'KE'`, `'KEN'` and `'Republic of Kenya'` are the same country, as are `'USA'`, `'US'`, `'united states'` and `'United States of America'`. ISO-2/ISO-3 codes, official names, common abbreviations (`UK`, `DRC`) and French/Spanish/Portuguese names all resolve; accents, case and punctuation are ignored, so `"Côte d'Ivoire"` and `'cote divoire'` both work. A name that doesn't match raises, with suggestions — it is never resolved to the nearest guess. Use `ssd.list_locations(which)` for the countries in a given dataset, `ssd.list_all_locations()` for every known location, and `ssd.resolve()`/`ssd.location_info()` to inspect the mapping.

## Installation

```bash
pip install starsim_data # or, from a clone: pip install -e .
```

---

# What's included

There are two families of data. `ssd.load()` returns a [Sciris](https://sciris.org) (`pandas`-compatible) dataframe whose shape depends on the dataset.

## 1. Demographics (UN World Population Prospects 2024)

Sourced from the [UN WPP 2024](https://population.un.org/wpp/), Medium variant, for 186 countries every 10 years from 1950 to 2100 (16 time points). Grouped in `demographics-2024.h5`, exposed as four datasets whose `load()` result is a [Starsim](https://starsim.org)-ready dataframe with UN-native column names:

| `which=` | What it is | Age resolution | Columns returned |
|---|---|---|---|
| `births` | Crude birth rate (per 1,000) | none (national) | `[Time, CBR]` |
| `deaths` | Age/sex mortality rate `m(x)` | 5-year abridged (`0, 1–4, 5–9, …, 100+`) | `[Time, Sex, AgeGrpStart, mx]` |
| `migration` | Crude net-migration rate (per 1,000) | none (national) | `[Time, CNMR]` |
| `population` | Population counts (absolute persons) | 5-year (`0–4, 5–9, …, 100+`) | `[Time, Sex, AgeGrp, Value]` |

These drop straight into Starsim: `deaths` matches `ss.Deaths`'s expected columns, `births` feeds `ss.Births`/`ss.Pregnancy`, and `population` gives age–sex pyramids for initialization.

**Not included:**

- ❌ Annual resolution — only every 10th year (1950, 1960, …, 2100).
- ❌ Subnational demographics (states, provinces, counties).
- ❌ Age-specific fertility (births are the crude rate only) or age-specific migration (crude rate only) — the UN provides no age breakdown for these.
- ❌ "Both sexes"/"Total" rows (Female + Male only) and non-Median projection variants.
- ❌ Namibia, for now — it was dropped by a bug that read its ISO-2 code `NA` as "missing". The bug is fixed but the data needs refetching; see [CHANGELOG.md](CHANGELOG.md). Namibia's contact matrices were never affected.

Demographic data is versioned by UN WPP revision. `load()` reads the newest bundled revision; pass `revision=` to pin an older one, and see `ssd.list_revisions()` for what's available. A new WPP release therefore adds a store rather than changing data already in use.

## 2. Contact matrices

*Note: These data were adapted from the excellent [Epydemix](https://github.com/epistorm/epydemix-data) project*

Age-structured contact rates — the average number of contacts between age groups — across five settings (`all`, `home`, `work`, `school`, `community`), selected with the `kind=` argument. `load()` returns a square dataframe whose rows and columns are indexed by the start age of each bin (e.g. `0, 5, …, 75`), so you can select by age with `M.loc[25, 30]`. Data included are a trimmed subset of [epydemix-data](https://github.com/epistorm/epydemix-data):

| `which=` | Matrix | Age groups | Countries | Source study |
|---|---|---|---|---|
| `prem2017` | 16×16 | 5-year (`0–4, …, 75+`) | 152 | [Prem et al. 2017](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005697) |
| `prem2021` | 16×16 | 5-year (`0–4, …, 75+`) | 177 | [Prem et al. 2021](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009098) |
| `mistry2021` | 85×85 | single-year (`0–84`, last is `84+`) | 36 | [Mistry et al. 2021](https://www.nature.com/articles/s41467-020-20544-y) |

Not every country has every source; use `ssd.list_locations('prem2021')` etc. to check. 

*Note:* `epydemix` has additional datasets for subnational contact matrices that are not included here.

---

## Geographies

All data is level 0 (country). 187 distinct countries appear across the datasets; coverage varies by source (186 for demographics; 36–177 for contact matrices). Canonical keys use `_` for spaces (e.g. `United_States`, `Sierra_Leone`), but you can pass any recognized name, code or alias — see the resolution rules above. The bundled `locations.csv` lists each country's ISO 3166-1 alpha-2 and alpha-3 codes, official name, aliases and available contact sources; `ssd.location_info(location)` returns a row of it.

`ssd.parse_level()` accepts `'admin1'`, `'ADM2'`, `'3'` or a bare integer. Nothing above level 0 has data yet; it exists so the vocabulary is settled before subnational data arrives.

## Citing

When you use these data, cite the underlying sources: the [UN World Population Prospects 2024](https://population.un.org/wpp/) for demographics, and the relevant contact-matrix study (Prem 2017, Prem 2021, and/or Mistry 2021) for each source you use. See [NOTICE.md](NOTICE.md) for full attributions.

Each dataset also carries its attribution as data. `ssd.provenance(which)` returns the source, URL, license, citation and build details for a dataset, and every frame from `load()` has the same in `df.attrs['provenance']` — so the citation travels with the data rather than needing to be looked up:

```python
ssd.provenance('mistry2021').citation   # 'Mistry D, Litvinova M, ...'
ssd.provenance('deaths').license        # 'CC BY 3.0 IGO'
```

## Building from source

The bundled `.h5` files are generated from the human-readable sources in [`raw_data/`](raw_data/) by the scripts in [`scripts/`](scripts/). See those folders' READMEs to regenerate or update the data.

## License

The repository's code, packaging, and curation are licensed under the [MIT License](LICENSE).

The bundled data files are third-party datasets under their own upstream licenses — the UN WPP data under its [terms of use](https://population.un.org/wpp/), and the contact matrices under **Apache-2.0** (`mistry2021`) and **GPL-3.0** (`prem2017`/`prem2021`) — not under MIT. Full upstream license texts are in [`licenses/`](licenses/), and [NOTICE.md](NOTICE.md) has the per-source details and required attributions.
