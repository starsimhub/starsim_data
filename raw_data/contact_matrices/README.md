# raw_data/contact_matrices — source contact matrices

This folder is the **source of truth** for the contact matrices: the raw, human-readable CSVs, one folder per country. It is *not* shipped in the installed package — it is the input from which the bundled HDF5 stores (`starsim_data/data/*.h5`) are built.

## Provenance

These CSVs are derived from [epydemix-data](https://github.com/epistorm/epydemix-data), the data companion to the [Epydemix](https://github.com/epistorm/epydemix) epidemic modeling library. We took epydemix-data as the upstream source and trimmed it down to just what Starsim needs: the **national (level 0) contact matrices**, with each country holding its CSVs directly (rather than epydemix-data's nested per-source subfolders). We keep the `mistry2021`, `prem2021`, and `prem2017` sources and drop epydemix-data's demographic/age-distribution data, its other subnational geographies, the `litvinova_2025` source, and the US sex/race-ethnicity attributes. The contact-rate values themselves are unchanged from epydemix-data, which in turn sourced them from the studies cited in the [top-level README](../../README.md). See [NOTICE.md](../../NOTICE.md) for the per-source upstream licenses that continue to apply to these files.

The US states were added later, by `scripts/download_epydemix.py`, from a pinned commit of epydemix-data: one folder per state, named like `United_States__Massachusetts` (the `__` stands for the `:` of the location key `United_States:Massachusetts`, which a folder name can't hold on every platform), holding the Mistry et al. 2021 matrices as `mistry2021_us_contacts_<setting>.csv`.

## Layout

Each country folder contains one CSV per `(source, setting)` combination, named `<source>_contacts_<setting>.csv`:

- `<source>` — one of `mistry2021`, `prem2021`, `prem2017` (whichever are available for that country), or `mistry2021_us` for a US state.
- `<setting>` — one of `all`, `home`, `work`, `school`, `community`.

```
raw_data/contact_matrices/
├── Kenya/
│   ├── prem2017_contacts_all.csv
│   ├── prem2017_contacts_home.csv
│   └── ...
└── ...
```

Each CSV is a square matrix of contact rates with no header and no index. Matrix sizes by source:

- `mistry2021`, `mistry2021_us` — 85×85, single-year age groups (0–84, last group is 84+).
- `prem2021` / `prem2017` — 16×16, 5-year age groups (0–4, 5–9, …, 75+).

The country list and per-country ISO codes / available sources live in `starsim_data/data/locations.csv` (the single canonical copy, bundled with the package). See the [top-level README](../../README.md) for the column descriptions.

## Editing

These CSVs are the origin of the packaged contact-matrix data. After changing anything here (adding a country, a source, or correcting values), rebuild the bundled HDF5 stores:

```bash
python scripts/build_hdf5.py --check
```

Do **not** hand-edit the generated `starsim_data/data/*.h5` files — they are always regenerated from these CSVs.
