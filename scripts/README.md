# scripts — data build tooling

Dev/CI-only scripts for turning the raw CSV tree into the bundled data files. These are **not** part of the installed package and are not imported at runtime.

## build_hdf5.py

Walks [`raw_data/`](../raw_data/) and writes one HDF5 file per dataset (contact source) into [`starsim_data/data/`](../starsim_data/data/), plus a copy of `locations.csv`. Each store is keyed by location, with one dataset per contact setting; matrices are cast to `float32` and compressed with gzip9 + byte-shuffle.

```bash
python scripts/build_hdf5.py            # rebuild all datasets found in raw_data
python scripts/build_hdf5.py --check    # also round-trip validate against the CSVs
```

Run this whenever `raw_data/` changes. Adding a new dataset requires no code change here — drop its `<source>_contacts_<setting>.csv` files into the country folders and re-run; the script discovers sources automatically, and `starsim_data.list_datasets()` will pick up the new `.h5`.

Requires `h5py`, `numpy`, and `pandas` (all runtime/dev dependencies of the package).
