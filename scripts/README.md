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

Walks [`raw_data/contact_matrices/`](../raw_data/contact_matrices/) and writes one HDF5 file per dataset (contact source). Each store is keyed by location, with one dataset per contact setting; matrices are cast to `float32` and compressed with gzip9 + byte-shuffle. The sources in `BUNDLED` (`prem2021`) go into [`starsim_data/data/`](../starsim_data/data/), along with `prem/prem2017.h5`, the `prem2017` matrices for the ten locations `prem2021` lacks, which the default contact matrices use. The others are fetched on demand, so their stores go into [`fetched/`](../fetched/), outside the package, and are rebuilt only with `--fetched` (a rebuild changes their bytes, and `fetch()` downloads them from the GitHub release named in `RELEASE`, where they are assets). Every run rewrites the manifest `starsim_data/data/fetched.json` from the stores in `fetched/`.

```bash
python scripts/build_hdf5.py              # rebuild prem2021.h5 and the manifest
python scripts/build_hdf5.py --check      # also round-trip validate against the CSVs
python scripts/build_hdf5.py --fetched    # also rebuild the stores in fetched/
python scripts/build_hdf5.py --fetched population_us   # ...or only those named
```

Run this whenever `raw_data/` changes. A new source is discovered automatically from its `<source>_contacts_<setting>.csv` files: add it to `BUNDLED`, or make it a fetched one. The existing sources are published and won't change; adding a fetched one means listing it in `FETCHED_SOURCES`, building it with `--fetched`, setting a new tag in `RELEASE`, and creating that release once the change is on `main`, with `publish.py` (below).

It also builds `fetched/population_us.h5`, the US states' populations, from `raw_data/population_us.csv`, and writes each state's matrices under the location key `United_States:Massachusetts` (from the folder `United_States__Massachusetts`).

## download_epydemix.py

Copies the US states' contact matrices (Mistry et al. 2021) and populations (US Census Bureau, 2023) from a pinned commit of [epydemix-data](https://github.com/epistorm/epydemix-data) into `raw_data/`, checking that each state is in the node table under the same name. No token needed.

```bash
python scripts/download_epydemix.py                         # -> raw_data/
python scripts/build_hdf5.py --fetched mistry2021_us population_us
```

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

## build_nodes.py

Builds `nodes.h5` — the bundled node table: centroids, geodesic areas, p-codes and hierarchy for administrative levels 0 and 1, worldwide.

```bash
python scripts/build_nodes.py --check    # ~1.4 GB of downloads on a cold cache
python scripts/build_nodes.py --limit 5  # a quick subset, for development
```

Boundaries come from UNOCHA COD-AB where the [laser-base mirror](https://github.com/laser-base/unocha) has the country (~110 of them, and the reason the table has p-codes at all) and from the two global geoBoundaries CGAZ v6.0.0 GeoPackages otherwise. The two do not always agree on how a country subdivides, so each row records its `source`. Downloads go through the package cache, so a rebuild after the first is fast.

The script refuses to draw on any source whose descriptor says `redistributable=False` — that is how GADM's non-commercial license is kept out of bundled data, rather than by remembering.

National population is read from this package's own bundled WPP data. Level-1 population is WorldPop's 2020 raster summed within each unit, a ~1 GB download paid once here rather than by every user; other years and finer levels are left to `ssd.fetch_nodes()`.

Needs the `[spatial]` extra as well as `[dev]`: `pip install -e ".[dev,spatial]"`.

## publish.py

Makes a release, from an up-to-date `main`: the data release named on the command line (unless it already exists), with the stores in [`fetched/`](../fetched/) as assets, then `v<version>`, with the version from `starsim_data/version.py` and the notes from its section of the changelog. Publishing that triggers [`publish.yml`](../.github/workflows/publish.yml), which publishes the package to PyPI. It first checks that every store in the manifest is downloaded from that data release and that `fetched/` holds the same bytes.

```bash
python scripts/publish.py data-2026.10 --dry-run  # check everything, create nothing
python scripts/publish.py data-2026.10
```

## Dependencies

These scripts require `h5py`, `numpy`, `pandas`, plus `pycountry` for `build_locations.py` and `geopandas`/`pyogrio` for `build_nodes.py` — `pip install -e ".[dev,spatial]"` covers all of them. `provenance.py` is a shared helper, not a script: it stamps each store with its source, license, citation and build details, which `starsim_data.provenance()` then reads back.
