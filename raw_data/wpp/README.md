# raw_data/wpp — UN World Population Prospects source files

This folder holds the **UN WPP source CSVs** used to build `starsim_data/data/demographics.h5` (which groups the births, deaths, migration, and population series). The CSVs are external data and are **not committed** (`.gitignore` keeps only this README); regenerate them with the download script below, or drop in bulk files manually. Either way they are a citable, versioned UN release, so re-fetching a given revision reproduces the data.

## Option A (recommended): download via the API

`scripts/download_wpp.py` pulls exactly the indicators this package needs, for its countries, at decadal years 1950–2100, and writes three normalized CSVs here (`wpp_indicators.csv`, `wpp_lifetable.csv`, `wpp_population.csv`).

It needs a **Bearer token** in `scripts/.env` (register free at the [UN WPP Data Portal](https://population.un.org/dataportal) — the data endpoints require it, though the indicator/location metadata endpoints are open). The `.env` file is git-ignored. Then:

```bash
python scripts/download_wpp.py                 # writes raw_data/wpp/wpp_*.csv
python scripts/build_demographics.py --check    # builds starsim_data/data/*.h5
```

`download_wpp.py --skip-existing` re-fetches only the series whose CSVs are missing.

## Option B: manual bulk download

Alternatively, download these from the [WPP download page](https://population.un.org/wpp/downloads) in **CSV format**, **Medium variant**, 1950–2100, and drop them here (gzipped `.csv.gz` is fine). Exact filenames don't matter — `build_demographics.py` classifies each file by its columns.

| Dataset | Builds group | Required columns |
|---|---|---|
| **Demographic Indicators** (comprehensive) | `/births` (CBR), `/migration` (CNMR) | `ISO2_code`, `Time`, `CBR`, `CNMR` |
| **Abridged Life Table** (estimates + projection halves) | `/deaths` | `ISO2_code`, `Time`, `Sex`, `AgeGrpStart`, `mx` |
| **Population by 5-year age groups and sex** | `/population` | `ISO2_code`, `Time`, `AgeGrp` (or `AgeGrpStart`), `PopMale`, `PopFemale` |

## Notes

- Only **Female** and **Male** are kept (WPP's "Total"/"Both sexes" rows are dropped), matching Starsim's `ss.Deaths` sex conventions.
- Birth and net-migration rates are **crude national rates** (no age dimension) — this is all UN WPP provides for them, and it matches what `ss.Births`/`ss.Pregnancy` consume.
- Deaths use the **abridged** age bins (`0, 1–4, 5–9, …, 100+`); population uses **5-year** groups (`0–4, 5–9, …, 100+`).
- Population counts are **absolute persons** (verified: Kenya 2020 ≈ 52.2M, India 2020 ≈ 1.4B).
- Region aggregates ("Americas", etc.) that share a country's ISO2 code are excluded (the download script drops any WPP location without coordinates).
