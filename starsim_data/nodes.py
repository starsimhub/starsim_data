"""
The node table: metapopulation geography without the geometry.

A spatial model mostly needs to know, for each administrative unit, *where it is*, *how
big it is* and *how many people live there* -- not the exact shape of its border. Reduced
to that, the whole world at admin 0 and 1 is a few hundred KB, needs no geospatial
libraries to read, and ships inside the wheel like everything else in tier 0.

```python
import starsim_data as ssd
ssd.load_nodes('kenya')             # one row: the country
ssd.load_nodes('kenya', level=1)    # 47 counties: centroids, areas, p-codes
ssd.distances('kenya', level=1)     # the 47x47 great-circle distance matrix, in km
ssd.adjacency('kenya', level=1)     # which of the 47 counties share a border
```

Columns are `nodeid`, `location`, `iso3`, `level`, `name`, `pcode`, `dot_name`, `parent`,
`lat`, `lon`, `area_km2`, `population` and `source`.

Two of those deserve a note. **`pcode`** is the join key: for UNOCHA-sourced rows it is
the humanitarian p-code that essentially all subnational health data is keyed on, and it
is what joins a node back to its full geometry. **`dot_name`** is the readable
hierarchical path (`Kenya:Baringo`), in this package's canonical spelling, so that
`dot_name.split(':')[0]` is always a location `load()` accepts.

`population` is UN WPP at level 0, and WorldPop (1 km, UN-adjusted, 2020) summed within
each unit at level 1, worked out when the table is built. Other years, and finer levels,
need the raster aggregation at the time of use, which is a download rather than a
lookup, so they live behind `download_nodes()` in `starsim_data.rasters`.

Full geometry -- actual polygons, for maps and exact spatial operations -- is
`starsim_data.shapes`, and needs the `[spatial]` extra.
"""

import unicodedata
import numpy as np
import sciris as sc
import starsim_data as ssd

__all__ = ['load_nodes', 'distances', 'adjacency', 'node_name']

EARTH_RADIUS_KM = 6371.0088 # IUGG mean radius

UNITS = {'km': 1.0, 'm': 1000.0, 'mi': 0.621371, 'miles': 0.621371}


def node_name(name):
    """Render an administrative unit's name in this package's canonical style.

    `New York` -> `New_York`, `Ile-de-France` -> `Ile_de_France`. The same accent- and
    punctuation-folding as `locations.normalize`, but case is preserved: a `dot_name` is
    read by people as well as matched by machines.

    Shared by the node-table build and by `download_shapes()`, so that a shape's `dot_name`
    is always the same string as its node's.
    """
    decomposed = unicodedata.normalize('NFKD', str(name or '').strip())
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = ''.join(' ' if c in '-_/' else c for c in stripped if c.isalnum() or c in ' -_/')
    return '_'.join(cleaned.split())


def load_nodes(location, level=0):
    """
    Load the node table for a location: centroids, areas, p-codes and hierarchy.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        level (int/str): administrative level -- 0 for the country itself, 1 for its
            first-level subdivisions. Accepts `'admin1'` / `'ADM1'` / `1`; see
            `parse_level()`. None returns every level at once.

    Returns:
        sciris.dataframe: one row per administrative unit, with columns `nodeid`,
        `location`, `iso3`, `level`, `name`, `pcode`, `dot_name`, `parent`, `lat`, `lon`,
        `area_km2`, `population` and `source`. Provenance is in `.attrs['provenance']`.

    Raises:
        KeyError: if the location is unknown, or has no boundaries in the node table.
        ValueError: if the level is not available.

    Example:
        ```python
        import starsim_data as ssd
        ssd.load_nodes('kenya', level=1).shape[0] # Returns 47
        ```
    """
    return ssd.load(location, which='nodes', level=level)


def _coordinates(location, level, nodes):
    """Return the node table and its centroid coordinates in radians."""
    if nodes is None:
        nodes = load_nodes(location, level=level)
    if not len(nodes):
        raise ValueError(f'no nodes for {location!r} at level {level}')
    lat = np.radians(nodes.lat.to_numpy())
    lon = np.radians(nodes.lon.to_numpy())
    return nodes, lat, lon


def _check_index(nodes, index):
    """Check that `index` is a column of the node table."""
    if index not in nodes.columns:
        raise ValueError(f'index must be a column of the node table, not {index!r}; available: {list(nodes.columns)}')
    return


def distances(location=None, level=1, nodes=None, units='km', index='dot_name'):
    """
    Great-circle distances between node centroids -- the input a gravity model needs.

    The gravity formulation itself (`c_ij = k * P_i^a * P_j^b / D_ij^c`) belongs in the
    model, not in a data package: this provides `D_ij`, and `load_nodes()` provides `P_i`.

    Distances are great-circle (haversine) on a spherical Earth, which is within about
    0.5% of the geodesic distance -- far inside the uncertainty of treating an
    administrative unit as a point in the first place.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        level (int/str): administrative level to use (default 1, the subdivisions).
        nodes (dataframe): use this node table instead of loading one, e.g. one from
            `download_nodes()` with population filled in, or a subset.
        units (str): `'km'` (default), `'m'`, or `'mi'`.
        index (str): which column labels the rows and columns -- `'dot_name'` (default),
            `'pcode'`, `'name'` or `'nodeid'`.

    Returns:
        sciris.dataframe: a square, symmetric matrix with a zero diagonal.

    Raises:
        ValueError: if `units` or `index` is not recognized, or there are no nodes.

    Example:
        ```python
        import starsim_data as ssd
        d = ssd.distances('kenya', level=1)
        d.loc['Kenya:Nairobi', 'Kenya:Mombasa'] # Returns 433.1 (km)
        ```
    """
    if units not in UNITS:
        raise ValueError(f'units must be one of {sorted(UNITS)}, not {units!r}')
    nodes, lat, lon = _coordinates(location, level, nodes)
    _check_index(nodes, index)

    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    haversine = np.sin(dlat/2)**2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon/2)**2
    haversine = np.clip(haversine, 0, 1) # Floating-point error can push a self-distance fractionally above 1, and turn a zero on the diagonal into a NaN
    matrix = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine))
    np.fill_diagonal(matrix, 0.0)

    labels = list(nodes[index])
    return sc.dataframe(matrix * UNITS[units], index=labels, columns=labels)


def _shape_adjacency(group, key, spec, opts):
    """The pairs of units that share a border, as a frame of `level`, `a` and `b` (nodeids, a < b)."""
    data = group[key][()]
    return sc.dataframe(data, columns=spec['columns'])


ssd.registry.register_layout('adjacency', _shape_adjacency)


def adjacency(location=None, level=1, nodes=None, index='dot_name'):
    """
    Which administrative units share a border: a square boolean matrix.

    Worked out from the polygons when the node table is built (units within about 100 m
    of each other count as touching, which absorbs slivers between neighboring
    polygons), so it needs no geospatial libraries and no download.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        level (int/str): administrative level (default 1; level 1 is the finest bundled).
        nodes (dataframe): label the rows and columns from this node table instead of
            loading one, e.g. one from `download_nodes()` with population filled in; it
            must be the units of `location` at `level`, in `nodeid` order or a subset.
            A table from `download_nodes()` at a level that is not bundled carries its own
            borders, so any level works that way.
        index (str): which column labels the rows and columns -- `'dot_name'` (default),
            `'pcode'`, `'name'` or `'nodeid'`.

    Returns:
        sciris.dataframe: a square, symmetric boolean matrix with a false diagonal.

    Raises:
        ValueError: if the level has no bundled borders, or `index` is not recognized.

    Example:
        ```python
        import starsim_data as ssd
        a = ssd.adjacency('kenya', level=1)
        a.loc['Kenya:Nairobi', 'Kenya:Kiambu'] # Returns True: they share a border
        ```
    """
    level = ssd.parse_level(level)
    if nodes is None:
        nodes = load_nodes(location, level=level)
    _check_index(nodes, index)
    labels = list(nodes[index])

    # Borders worked out by download_nodes(), at a level that is not bundled
    if nodes.attrs.get('borders') is not None:
        pairs = np.asarray(nodes.attrs['borders'], dtype=int).reshape(-1, 2)
        matrix = np.zeros((len(nodes), len(nodes)), dtype=bool)
        matrix[pairs[:, 0], pairs[:, 1]] = True
        return sc.dataframe(matrix | matrix.T, index=labels, columns=labels)

    # Otherwise, the bundled borders
    adj = ssd.registry.datasets().get('adjacency')
    if (adj is None) or (level not in adj.levels):
        bundled = list(adj.levels) if adj else []
        raise ValueError(f'no borders are bundled at level {level}; the bundled levels are {bundled}')
    if location is None:
        location = str(nodes.location.iloc[0])
    pairs = ssd.load(location, which='adjacency')
    pairs = pairs[pairs.level == level]
    n = max(int(nodes.nodeid.max()), int(pairs[['a', 'b']].to_numpy().max(initial=-1))) + 1 # Big enough for every nodeid, in the table or in the pairs
    matrix = np.zeros((n, n), dtype=bool)
    matrix[pairs.a.to_numpy(), pairs.b.to_numpy()] = True
    matrix |= matrix.T
    ids = nodes.nodeid.to_numpy().astype(int)
    return sc.dataframe(matrix[np.ix_(ids, ids)], index=labels, columns=labels)
