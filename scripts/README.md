# scripts — data build tooling

Dev/CI-only scripts for turning the raw CSV tree into the bundled data files. These are **not** part of the installed package and are not imported at runtime.

## build_locations.py

Fills the derived columns of [`starsim_data/data/locations.csv`](../starsim_data/data/locations.csv) — `iso3`, `official_name` and `aliases` — from `pycountry`, joining on the hand-maintained ISO-2 code. Those columns are what `starsim_data.locations` matches against at runtime, so `pycountry` is a build-time dependency only. Aliases that would be ambiguous across locations are dropped with a warning.

```bash
python scripts/build_locations.py            # rewrite locations.csv in place
python scripts/build_locations.py --check    # report what would change, write nothing
```

Re-run after adding a location, or to pick up a newer `pycountry`.

## build_hdf5.py

Walks [`raw_data/contact_matrices/`](../raw_data/contact_matrices/) and writes one HDF5 file per dataset (contact source) into [`starsim_data/data/`](../starsim_data/data/). Each store is keyed by location, with one dataset per contact setting; matrices are cast to `float32` and compressed with gzip9 + byte-shuffle.

```bash
python scripts/build_hdf5.py            # rebuild all datasets found in raw_data
python scripts/build_hdf5.py --check    # also round-trip validate against the CSVs
```

Run this whenever `raw_data/` changes. Adding a new dataset requires no code change here — drop its `<source>_contacts_<setting>.csv` files into the country folders and re-run; the script discovers sources automatically, and `starsim_data.list_datasets()` will pick up the new `.h5`.

## download_wpp.py

Downloads the UN World Population Prospects data this package needs (via the WPP Data Portal API) into [`raw_data/demographics/`](../raw_data/demographics/) as normalized CSVs. Requires a Bearer token in `scripts/.env` (git-ignored; register free at the WPP data portal). See that folder's README for the token setup and the manual-download alternative.

```bash
python scripts/download_wpp.py                 # -> raw_data/demographics/wpp_*.csv
python scripts/download_wpp.py --skip-existing  # only fetch missing series
```

## build_demographics.py

Builds `demographics-<revision>.h5` (a group per series: `births`, `migration`, `deaths`, `population`) from the WPP CSVs in [`raw_data/demographics/`](../raw_data/demographics/) (produced by `download_wpp.py`, or downloaded manually), then:

```bash
python scripts/build_demographics.py --check
```

It classifies each WPP CSV by its columns (so exact filenames don't matter), filters to the package's countries and to decadal years 1950–2100, and writes tidy stores keyed by location. Birth and migration are crude national rates; deaths are age/sex-specific mortality (`mx`, 5-year abridged bins); population is by 5-year age groups and sex (absolute persons).

These scripts require `h5py`, `numpy`, `pandas` and (for `build_locations.py`) `pycountry` — all installed by `pip install -e ".[dev]"`. `provenance.py` is a shared helper, not a script: it stamps each store with its source, license, citation and build details, which `starsim_data.provenance()` then reads back.
