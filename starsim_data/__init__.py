"""
starsim_data: national-level demographic data and contact matrices for disease
modeling with Starsim.

This package bundles UN World Population Prospects demographics (births, deaths,
migration, population, fertility) and a trimmed, reorganized subset of the contact-matrix data
from epydemix-data (https://github.com/epistorm/epydemix-data), national-level (level
0) only. See NOTICE.md for per-source data licenses and attributions.

The data ships bundled as HDF5 under `starsim_data/data/` (e.g. `prem2021.h5`,
`demographics-2024.h5`). `load` returns a `sciris.dataframe` (a drop-in replacement for
a pandas `DataFrame`); for contact matrices the rows and columns are indexed by the
start age of each bin:

```python
import starsim_data as ssd
M = ssd.load(location='kenya')                    # square, age-indexed (0, 5, ..., 75)
M.loc[25, 30]                                      # contacts between the 25-29 and 30-34 bins
```

Locations can be given as a name, ISO-2/ISO-3 code, official name or alias -- `'USA'`,
`'US'`, `'united states'` and `'United_States'` all resolve to the same data. Every
dataset records where it came from; see `provenance()`.

`load` never touches the network. The full `prem2017` and `mistry2021` contact matrices
are published with this package's releases, and `fetch()` downloads, verifies and caches
them. What this package does not publish -- annual series, complete life tables, other
projection variants, boundaries and gridded population -- comes from the organizations
that do, through `download()` and the other `download_*` functions; see `cache_info()`
and `options`. `plot()` draws the data for a quick check before it goes into a model.
"""

# This is the one module that uses `from` imports, to assemble the public namespace.
# Everywhere else in the package, follow Starsim's convention: `import starsim_data as
# ssd` and reach things as `ssd.load`, `ssd.registry.datasets()` and so on. The order
# below matters, because a few modules register themselves on import: `registry` has to
# exist before `loaders` adds its layouts, and before `downloading` adds its datasets.
from .version import __version__, __versiondate__, __license__
from .settings import options
from . import registry
from .registry import register_dataset, register_layout
from .locations import resolve, location_info, list_all_locations, parse_level
from .loaders import load, list_datasets, list_locations, list_revisions, provenance
from .cache import cache_dir, cache_info, cache_provenance, cached_download, clear_cache
from .downloading import download, list_downloadable
from .fetching import fetch, list_fetchable
from .plotting import plot, choropleth
from .nodes import load_nodes, distances, adjacency, node_name
from .shapes import download_shapes, list_shape_sources, fetch_shapes
from .rasters import download_nodes, download_raster, aggregate_raster, rescale_to_national, fetch_nodes, fetch_raster

__all__ = ['load', 'fetch', 'download', 'plot', 'choropleth', 'provenance', 'options', 'registry',
           'load_nodes', 'distances', 'adjacency', 'node_name',
           'download_shapes', 'list_shape_sources',
           'download_nodes', 'download_raster', 'aggregate_raster', 'rescale_to_national',
           'list_datasets', 'list_locations', 'list_revisions', 'list_fetchable', 'list_downloadable',
           'resolve', 'location_info', 'list_all_locations', 'parse_level',
           'register_dataset', 'register_layout',
           'cache_dir', 'cache_info', 'cache_provenance', 'cached_download', 'clear_cache']
