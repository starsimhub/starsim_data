# starsim_data/data — bundled data files

**Generated — do not edit by hand.** These files ship inside the installed package and are the data that `starsim_data.load()` reads.

- `<source>.h5` — one HDF5 store per contact source (e.g. `prem2017.h5`, `prem2021.h5`, `mistry2021.h5`). Each is keyed by location with one `float32` dataset per contact setting: `/<Location>/<setting>`.
- `locations.csv` — country metadata (ISO code, available sources, etc.).

All of these are built from [`raw_data/`](../../raw_data/) by [`scripts/build_hdf5.py`](../../scripts/build_hdf5.py). To regenerate:

```bash
python scripts/build_hdf5.py --check
```

The national-tier `.h5` files are small (a few MB each) and committed to the repo so that `pip install` is self-contained; this is a deliberate exception to the `*.h5` rule in `.gitignore`. Any larger (e.g. subnational) tiers added later should be distributed as release assets instead of committed here.
