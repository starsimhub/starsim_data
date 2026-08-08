# raw_data — source data

The human-readable source data from which the bundled HDF5 stores in `starsim_data/data/` are built. Nothing here ships in the installed package; the build scripts in [`scripts/`](../scripts/) turn these inputs into the `.h5` files that do.

- [`contact_matrices/`](contact_matrices/) — per-country contact-matrix CSVs (`mistry2021`, `prem2021`, `prem2017`), the source for `starsim_data/data/*.h5`. Built by `scripts/build_hdf5.py`.
- [`demographics/`](demographics/) — UN World Population Prospects CSVs (births, deaths, migration, population), the source for `starsim_data/data/demographics-<revision>.h5`. Built by `scripts/build_demographics.py` (and fetched by `scripts/download_wpp.py`).

The canonical country/ISO metadata (`locations.csv`) lives in `starsim_data/data/` rather than here, since it is bundled with the package and read by all three scripts.

See each subfolder's README for details, provenance, and how to regenerate.
