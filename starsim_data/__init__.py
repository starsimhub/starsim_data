"""
starsim_data: national-level demographic data and contact matrices for disease
modeling with Starsim.

This package bundles UN World Population Prospects demographics (births, deaths,
migration, population) and a trimmed, reorganized subset of the contact-matrix data
from epydemix-data (https://github.com/epistorm/epydemix-data), national-level (level
0) only. See NOTICE.md for per-source data licenses and attributions.

The data ships bundled as HDF5 under `starsim_data/data/` (e.g. `prem2017.h5`,
`demographics-2024.h5`). `load` returns a `sciris.dataframe` (a drop-in replacement for
a pandas `DataFrame`); for contact matrices the rows and columns are indexed by the
start age of each bin:

```python
import starsim_data as ssd
M = ssd.load(location='kenya', which='prem2017')  # square, age-indexed (0, 5, ..., 75)
M.loc[25, 30]                                      # contacts between the 25-29 and 30-34 bins
```

Locations can be given as a name, ISO-2/ISO-3 code, official name or alias -- `'USA'`,
`'US'`, `'united states'` and `'United_States'` all resolve to the same data. Every
dataset records where it came from; see `provenance()`.

`load` never touches the network. What is not bundled -- annual series, complete life
tables, other projection variants -- is available from `fetch()`, which downloads and
caches; see `cache_info()` and `options`. `plot()` draws the data for a quick check
before it goes into a model.
"""

__version__ = "0.3.0"

# This is the one module that uses `from` imports, to assemble the public namespace.
# Everywhere else in the package, follow Starsim's convention: `import starsim_data as
# ssd` and reach things as `ssd.load`, `ssd.registry.datasets()` and so on. The order
# below matters, because a few modules register themselves on import: `registry` has to
# exist before `loaders` adds its layouts, and before `fetching` adds its datasets.
from .settings import options
from . import registry
from .registry import register_dataset, register_layout
from .locations import resolve, location_info, list_all_locations, parse_level
from .loaders import load, list_datasets, list_locations, list_revisions, provenance
from .cache import cache_dir, cache_info, cache_provenance, cached_download, clear_cache
from .fetching import fetch, list_fetchable
from .plotting import plot

__all__ = ["load", "fetch", "plot", "provenance", "options", "registry",
           "list_datasets", "list_locations", "list_revisions", "list_fetchable",
           "resolve", "location_info", "list_all_locations", "parse_level",
           "register_dataset", "register_layout",
           "cache_dir", "cache_info", "cache_provenance", "cached_download", "clear_cache"]
