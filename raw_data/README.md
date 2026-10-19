# raw_data — source data

The human-readable source data from which the bundled HDF5 stores in `starsim_data/data/` are built. Nothing here ships in the installed package; the build scripts in [`scripts/`](../scripts/) turn these inputs into the `.h5` files that do.

- [`contact_matrices/`](contact_matrices/) — per-location contact-matrix CSVs (`mistry2021`, `prem2021`, `prem2017`, and `mistry2021_us` for the US states), the source for `starsim_data/data/prem2021.h5` and `fetched/*.h5`. Built by `scripts/build_hdf5.py`.
- `population_us.csv` — the population of each US state in 2023 by single year of age (US Census Bureau, via epydemix-data), as `location, age, population`; the source for `fetched/population_us.h5`. Downloaded by `scripts/download_epydemix.py`, built by `scripts/build_hdf5.py`.
- [`demographics/`](demographics/) — UN World Population Prospects CSVs (births, deaths, migration, population), the source for `starsim_data/data/demographics-<revision>.h5`. Built by `scripts/build_demographics.py` (and fetched by `scripts/download_wpp.py`).

The canonical country/ISO metadata (`locations.csv`) lives in `starsim_data/data/` rather than here, since it is bundled with the package and read by all three scripts.

See each subfolder's README for details, provenance, and how to regenerate.
