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
"""

from .loaders import load, list_datasets, list_locations, list_revisions, provenance
from .locations import resolve, location_info, list_all_locations, parse_level

__version__ = "0.2.0"

__all__ = ["load", "list_datasets", "list_locations", "list_revisions", "provenance",
           "resolve", "location_info", "list_all_locations", "parse_level"]
