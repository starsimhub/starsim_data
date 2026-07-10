# starsim_data/data — bundled data files

**Generated — do not edit by hand.** These files ship inside the installed package and are the data that `starsim_data.load()` reads.

Each store carries a root `spec` attribute recording its `layout`, so `load()` returns the right shape for it.

**Contact matrices** (`layout='matrix'`), built from [`raw_data/`](../../raw_data/) by [`scripts/build_hdf5.py`](../../scripts/build_hdf5.py):

- `<source>.h5` — one store per contact source (`prem2017.h5`, `prem2021.h5`, `mistry2021.h5`), keyed by location with one `float32` matrix per contact setting: `/<Location>/<setting>`.

**Demographic series** from UN WPP, all grouped in `demographics.h5`, built by [`scripts/build_demographics.py`](../../scripts/build_demographics.py). One group per series, each with its own `spec`:

- `/births`, `/migration` (`layout='crude'`) — one value per year (CBR, CNMR), per location.
- `/deaths` (`layout='mortality'`) — age/sex mortality rate `mx`, a `(year, sex, age)` array per location.
- `/population` (`layout='population'`) — population by 5-year age groups and sex (absolute persons), `(year, sex, age)` per location.

Plus `locations.csv` — country metadata (ISO code, available sources, etc.).

To regenerate:

```bash
python scripts/build_hdf5.py --check           # contact matrices, from raw_data/
python scripts/build_demographics.py --check   # demographics, from raw_data/wpp/
```

The national-tier `.h5` files are small (a few MB each) and committed to the repo so that `pip install` is self-contained; this is a deliberate exception to the `*.h5` rule in `.gitignore`. Any larger (e.g. subnational) tiers added later should be distributed as release assets instead of committed here.
