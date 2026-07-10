# raw_data — source contact matrices

This folder is the **source of truth**: the raw, human-readable CSV contact matrices, one folder per country. It is *not* shipped in the installed package — it is the input from which the bundled HDF5 stores are built.

## Provenance

These CSVs are derived from [epydemix-data](https://github.com/epistorm/epydemix-data), the data companion to the [Epydemix](https://github.com/epistorm/epydemix) epidemic modeling library. We took epydemix-data as the upstream source and trimmed it down to just what Starsim needs: the **national (level 0) contact matrices**, with the folder layout flattened so each country holds its CSVs directly (no nested `contact_matrices/` subfolders). We keep the `mistry2021`, `prem2021`, and `prem2017` sources and drop epydemix-data's demographic/age-distribution data, subnational geographies, the `litvinova_2025` source, and the US sex/race-ethnicity attributes. The contact-rate values themselves are unchanged from epydemix-data, which in turn sourced them from the studies cited in the [top-level README](../README.md). See [NOTICE.md](../NOTICE.md) for the per-source upstream licenses that continue to apply to these files.

## Layout

Each country folder contains one CSV per `(source, setting)` combination, named `<source>_contacts_<setting>.csv`:

- `<source>` — one of `mistry2021`, `prem2021`, `prem2017` (whichever are available for that country).
- `<setting>` — one of `all`, `home`, `work`, `school`, `community`.

```
raw_data/
├── locations.csv
├── Kenya/
│   ├── prem2017_contacts_all.csv
│   ├── prem2017_contacts_home.csv
│   └── ...
└── ...
```

Each CSV is a square matrix of contact rates with no header and no index. Matrix sizes by source:

- `mistry2021` — 85×85, single-year age groups (0–84, last group is 84+).
- `prem2021` / `prem2017` — 16×16, 5-year age groups (0–4, 5–9, …, 75+).

`locations.csv` lists every country, its ISO code, and which contact sources it has. See the [top-level README](../README.md) for the column descriptions and data provenance.

## Editing

These CSVs are the origin of the packaged data. After changing anything here (adding a country, a source, or correcting values), rebuild the bundled HDF5 stores:

```bash
python scripts/build_hdf5.py --check
```

Do **not** hand-edit the generated `starsim_data/data/*.h5` files — they are always regenerated from these CSVs.
