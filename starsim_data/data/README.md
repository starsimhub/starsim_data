# starsim_data/data — bundled data files

These files ship inside the installed package and are the data that `starsim_data.load()` reads. The `.h5` stores are **generated — do not edit by hand** (regenerate them from the sources in `raw_data/`); `locations.csv` is the one file here with hand-maintained content, described below.

Each store carries a root `spec` attribute recording its `layout`, so `load()` returns the right shape for it.

**Contact matrices** (`layout='matrix'`), built from [`raw_data/contact_matrices/`](../../raw_data/contact_matrices/) by [`scripts/build_hdf5.py`](../../scripts/build_hdf5.py):

- `prem2021.h5` — the bundled contact source, keyed by location with one `float32` matrix per contact setting: `/<Location>/<setting>`.
- `prem/prem2017.h5` — the same, for the ten locations `prem2021` lacks, from `prem2017`. Together with `prem2021.h5` these are the default contact matrices, `load(which='prem')`. It is in a subfolder so that it is not discovered as a dataset of its own.
- `fetched.json` — the manifest of the stores that are fetched rather than bundled (`prem2017`, `mistry2021`, and for the US states `mistry2021_us` and `population_us`): for each, its URL at a pinned commit, SHA-256, locations and provenance. Their stores, built the same way, are in [`fetched/`](../../fetched/) at the top of the repository, outside the package; `fetch()` downloads them.

**Demographic series** from UN WPP, all grouped in `demographics-<revision>.h5` (e.g. `demographics-2024.h5`), built by [`scripts/build_demographics.py`](../../scripts/build_demographics.py). One group per series, each with its own `spec`:

- `/births`, `/migration` (`layout='crude'`) — one value per year (CBR, CNMR), per location.
- `/deaths` (`layout='mortality'`) — age/sex mortality rate `mx`, a `(year, sex, age)` array per location.
- `/population` (`layout='population'`) — population by 5-year age groups and sex (absolute persons), `(year, sex, age)` per location.

**Node table** (`layout='nodes'`), built from UNOCHA COD-AB and geoBoundaries by [`scripts/build_nodes.py`](../../scripts/build_nodes.py):

- `nodes.h5` — one compound dataset per location, holding every administrative unit at levels 0 and 1: `nodeid`, `location`, `iso3`, `level`, `name`, `pcode`, `dot_name`, `parent`, `lat`, `lon`, `area_km2`, `population`, `source`. Read with `starsim_data.load_nodes()`.
- `adjacency.h5` — for each location and level, the pairs of units that share a border. Read with `starsim_data.adjacency()`.

Plus `locations.csv` — the canonical country metadata file, read by all the build scripts and by the runtime location resolver. It is **part source, part generated**: `location`, `level`, `iso_code`, `primary_contact_source`, `contact_sources` and `population_source` are hand-maintained, while `iso3`, `official_name` and `aliases` are filled by [`scripts/build_locations.py`](../../scripts/build_locations.py) from `pycountry`. Edit the former by hand; regenerate the latter.

Note that this file must be read with `keep_default_na=False` (or with the `csv` module, as the resolver does): Namibia's ISO-2 code is the string `NA`, which pandas' defaults turn into NaN.

To regenerate:

```bash
python scripts/build_locations.py --check      # locations.csv derived columns
python scripts/build_hdf5.py --check           # contact matrices, from raw_data/contact_matrices/
python scripts/build_demographics.py --check   # demographics, from raw_data/demographics/
python scripts/build_nodes.py --check          # node table, from the boundary sources
```

`build_nodes.py` is the odd one out: its inputs are too big for `raw_data/` and are downloaded into the package cache instead, so a cold rebuild pulls ~1.4 GB. That is why it is not part of the automatic reproducibility check in CI.

Each `.h5` also carries a root `provenance` attribute recording its source, license, citation and build details; see `starsim_data.provenance()`.

The national-tier `.h5` files are small (a few MB each) and committed to the repo so that `pip install` is self-contained; this is a deliberate exception to the `*.h5` rule in `.gitignore`. Any larger (e.g. subnational) tiers added later should be distributed as release assets instead of committed here.
