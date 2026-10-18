"""
Gridded population, and how to turn it into node populations.

This is the step that turns a boundary file into a metapopulation. `load_nodes()` gives
you where each administrative unit is and how big it is; what it cannot give you, without
a download, is how many people live in each one below the national level. That number
comes from summing a 1 km gridded population raster inside each unit's polygon:

```python
import starsim_data as ssd
nodes = ssd.fetch_nodes('kenya', level=1)   # the node table, with population filled in
ssd.distances('kenya', level=1)             # ... and the distances between them
```

Which is everything a gravity model needs: `P_i`, `P_j` and `D_ij`.

Requires the `[spatial]` extra (`pip install starsim_data[spatial]`), because reading
polygons and clipping rasters needs `geopandas` and `rastertoolkit`. Rasters are cached
like every other download; WorldPop's server is slow, so the first call for a country
takes a while and later ones do not.

A caution worth carrying: WorldPop's *constrained* estimates are modeled, not counted,
and they will not equal the UN WPP national total for the same year -- for Kenya 2020
they come out about 1% low. If a model needs the national total to match WPP exactly,
rescale: `nodes.population *= wpp_total / nodes.population.sum()`.
"""

import io
import tempfile
import contextlib
import numpy as np
import sciris as sc
import starsim_data as ssd

__all__ = ['fetch_nodes', 'fetch_raster', 'aggregate_raster', 'rescale_to_national']

WORLDPOP_LICENSE = 'CC BY 4.0'
WORLDPOP_URL = 'https://www.worldpop.org'
WORLDPOP_CITATION = 'WorldPop (www.worldpop.org), School of Geography and Environmental Science, University of Southampton. https://dx.doi.org/10.5258/SOTON/WP00645'

COAST_DISTANCE = 0.1 # Degrees (about 10 km): a populated cell this close to a unit, but in none, counts for the nearest

# WorldPop publishes two 1 km products over different year ranges, with different naming.
# The newer one is UN-adjusted and constrained to built settlement; the older is the
# UN-adjusted unconstrained series.
PRODUCTS = (
    dict(
        first = 2015,
        last  = 2030,
        url   = 'https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/{iso3}/v1/1km_ua/constrained/{lower}_pop_{year}_CN_1km_R2025A_UA_v1.tif',
        name  = 'Global_2015_2030 R2025A, 1 km, constrained, UN-adjusted',
    ),
    dict(
        first = 2000,
        last  = 2020,
        url   = 'https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/{year}/{iso3}/{lower}_ppp_{year}_1km_Aggregated_UNadj.tif',
        name  = 'Global_2000_2020, 1 km, UN-adjusted',
    ),
)


def _product(year):
    """Return the WorldPop product covering `year`, preferring the newer series."""
    for product in PRODUCTS:
        if product['first'] <= year <= product['last']:
            return product
    first = min(p['first'] for p in PRODUCTS)
    last = max(p['last'] for p in PRODUCTS)
    raise ValueError(f'WorldPop 1 km population is published for {first}-{last}, not {year}')


def _default_year():
    """The year the bundled node table uses for national population, so the two agree."""
    return int(ssd.provenance('nodes').get('population_year', 2020))


def fetch_raster(location, year=None, refresh=False, verbose=None):
    """
    Download a WorldPop 1 km gridded-population raster for a country, and cache it.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        year (int): the year to fetch (2000-2030). Defaults to the year the bundled node
            table uses for national population, so the two are comparable.
        refresh (bool): re-download even if the file is already cached.
        verbose (bool): report progress (default: `options.verbose`).

    Returns:
        pathlib.Path: the cached GeoTIFF.

    Raises:
        ValueError: if the year is outside WorldPop's range.
        KeyError: if WorldPop has no raster for this country and year.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.fetch_raster('kenya', year=2020)  # doctest: +SKIP
    """
    verbose = sc.ifelse(verbose, ssd.options.verbose)
    year = _default_year() if year is None else int(year)
    product = _product(year)
    key = ssd.resolve(location)
    iso3 = ssd.location_info(key).iso3

    url = product['url'].format(year=year, iso3=iso3, lower=iso3.lower())
    try:
        path = ssd.cached_download(url, filename=f'worldpop_{iso3}_{year}.tif', subdir='worldpop', refresh=refresh, verbose=verbose)
    except Exception as e: # An HTTP failure means "not published"
        raise KeyError(f'WorldPop has no {year} raster for {key} ({iso3}): {e}') from e

    # Small territories 404 into a zero-length file rather than an error; catch that here
    # instead of letting it surface as an inscrutable raster-reading failure
    if path.stat().st_size == 0:
        path.unlink()
        raise KeyError(f"WorldPop's {year} raster for {key} ({iso3}) is empty; the 1 km series does not cover every small territory")
    return path


def aggregate_raster(raster, shapes, by='pcode', nearest=None):
    """
    Sum a raster inside each polygon: zonal statistics, keyed by an attribute.

    Args:
        raster (str/Path): a GeoTIFF, e.g. from `fetch_raster()`.
        shapes (GeoDataFrame): polygons, e.g. from `fetch_shapes()`.
        by (str): the column of `shapes` to key the result on.
        nearest (float): if given, also count a cell whose center is in no polygon but
            within this distance (in degrees) of one, for the nearest: boundaries are
            simplified at the coast, so otherwise a coastal city or a small island loses
            its people.

    Returns:
        dict: `{key: total}` for each polygon.

    Raises:
        ImportError: if the `[spatial]` extra is not installed.
        ValueError: if `by` is not a column of `shapes`.

    Example:
        >>> import starsim_data as ssd
        >>> gdf = ssd.fetch_shapes('kenya', level=1)             # doctest: +SKIP
        >>> ssd.aggregate_raster(ssd.fetch_raster('kenya'), gdf)  # doctest: +SKIP
    """
    try:
        import rastertoolkit as rtk # Imported here since it is optional (the [spatial] extra), and `import starsim_data` must work without it
    except ImportError as e:
        raise ImportError('aggregate_raster() needs the optional geospatial dependencies; install them with: pip install starsim_data[spatial]') from e
    if by not in shapes.columns:
        raise ValueError(f'{by!r} is not a column of the shapes; available: {list(shapes.columns)}')
    if nearest:
        return _aggregate_window(raster, shapes, by, nearest=nearest)

    # rastertoolkit reads shapes with pyshp, so it wants a shapefile on disk rather than a
    # GeoDataFrame in memory
    with tempfile.TemporaryDirectory() as tmp:
        stem = sc.path(tmp, 'shapes')
        shapes[[by, 'geometry']].to_file(stem.with_suffix('.shp'), driver='ESRI Shapefile')
        try:
            with contextlib.redirect_stdout(io.StringIO()): # It prints per-shape progress
                totals = rtk.raster_clip(str(raster), str(stem), shape_attr=by, quiet=True)
        except AssertionError: # It refuses a raster whose edge is at -180 degrees, as some of WorldPop's are (Eritrea's covers the whole world)
            totals = _aggregate_window(raster, shapes, by)
    return totals


def _aggregate_window(raster, shapes, by, nearest=None):
    """
    Sum a raster inside each polygon, reading only the parts of it the polygons cover.

    The raster must be on a plain latitude/longitude grid with north at the top, as
    WorldPop's are. This is used where rastertoolkit can't be: for `nearest`, and for
    a raster that rastertoolkit refuses (one starting at -180°, as Eritrea's does).

    Each populated cell goes to the polygon its center is in. With `nearest` (in degrees),
    a cell whose center is in none of them, but within that distance of one, goes to the
    nearest: boundary polygons are simplified at the coast, so otherwise the people of a
    coastal city or a small island are dropped. Invalid polygons are repaired first.
    """
    import shapely  # Imported here rather than at the top since they come with the optional [spatial] extra,
    import tifffile # and `import starsim_data` must work without it

    geoms = shapely.make_valid(np.asarray(shapes.geometry.values))
    lon0, lat0, lon1, lat1 = shapely.total_bounds(geoms)
    pad = nearest or 0

    # Read the populated cells inside the polygons' bounds (plus the padding, if any)
    cells = []
    with tifffile.TiffFile(raster) as tif:
        page = tif.pages[0]
        x0, y0 = page.tags['ModelTiepointTag'].value[3:5]
        dx, dy = page.tags['ModelPixelScaleTag'].value[:2]
        nodata = page.tags['GDAL_NODATA'].value if 'GDAL_NODATA' in page.tags else None
        grid = sc.objdict(x0=x0, y0=y0, dx=dx, dy=dy, nodata=nodata)
        rows, cols = page.shape[:2]
        c0 = max(int((lon0 - pad - x0) // dx), 0)
        c1 = min(int((lon1 + pad - x0) // dx) + 1, cols)
        r0 = max(int((y0 - lat1 - pad) // dy), 0)
        r1 = min(int((y0 - lat0 + pad) // dy) + 1, rows)
        if not page.is_tiled: # Read it whole: only a raster in strips, which WorldPop's large ones are not
            cells.append(_populated(page.asarray()[r0:r1, c0:c1], r0, c0, grid))
        else: # Read only the tiles that cover the window
            th, tw = page.tilelength, page.tilewidth
            across = -(-cols // tw) # Tiles per row, rounding up
            for ty in range(r0 // th, (r1 - 1) // th + 1):
                for tx in range(c0 // tw, (c1 - 1) // tw + 1):
                    index = ty * across + tx
                    tif.filehandle.seek(page.dataoffsets[index])
                    tile = page.decode(tif.filehandle.read(page.databytecounts[index]), index)[0]
                    tile = np.asarray(tile).reshape(th, tw)
                    cells.append(_populated(tile, ty * th, tx * tw, grid))
    lon, lat, val = np.hstack(cells)

    # Give each cell to the polygon its center is in, or else (with `nearest`) to the nearest one
    tree = shapely.STRtree(geoms)
    points = shapely.points(lon, lat)
    owner = np.full(len(points), -1)
    inside, poly = tree.query(points, predicate='within')
    owner[inside] = poly # A cell on a shared border goes to one of the two
    if nearest:
        rest = np.flatnonzero(owner < 0)
        near, poly = tree.query_nearest(points[rest], max_distance=nearest, all_matches=False)
        owner[rest[near]] = poly
    owned = owner >= 0
    sums = np.bincount(owner[owned], weights=val[owned], minlength=len(geoms))
    return {key: float(total) for key, total in zip(shapes[by], sums)}


def _populated(block, row, col, grid):
    """
    The populated cells of a raster block whose top left is at (row, col).

    Args:
        block (array): the block of raster values.
        row (int): the raster row of the block's top edge.
        col (int): the raster column of the block's left edge.
        grid (objdict): the raster's origin (`x0`, `y0`), cell size (`dx`, `dy`) and `nodata` value.

    Returns:
        array: three rows -- the longitude and latitude of each populated cell's center, and its value.
    """
    block = np.asarray(block, dtype=float)
    if grid.nodata is not None:
        block[block == float(grid.nodata)] = 0
    i, j = np.nonzero(np.isfinite(block) & (block > 0))
    lon = grid.x0 + (col + j + 0.5) * grid.dx
    lat = grid.y0 - (row + i + 0.5) * grid.dy
    return np.vstack([lon, lat, block[i, j]])


def fetch_nodes(location, level=1, year=None, source=None, refresh=False, verbose=None):
    """
    The node table with `population` filled in, from WorldPop, at any level and year.

    `load_nodes()` is instant and offline, with populations for 2020 at levels 0 and 1.
    This downloads the boundaries and the population raster for a country, sums the
    raster inside each unit, and returns the same table with the numbers filled in.

    At a bundled level, the boundaries are fetched from whichever source the bundled node
    table used for this country, so the p-codes line up and the join is exact rather than
    by name. At a finer level (2 and up), the table is built from the boundaries
    themselves, as the bundled one is, and which units share a border is worked out too
    and kept in `.attrs['borders']`, for `adjacency(nodes=...)`.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        level (int/str): administrative level (default 1).
        year (int): population year (default: the node table's, so level 0 and level 1
            are for the same year).
        source (str): override the boundary source; see `list_shape_sources()`. Leaving
            this alone is usually right -- see above.
        refresh (bool): re-download even if the files are already cached.
        verbose (bool): report progress (default: `options.verbose`).

    Returns:
        sciris.dataframe: the node table for this location and level, with `population`
        filled and `population_source` / `population_year` recorded in
        `.attrs['provenance']`.

    Raises:
        ImportError: if the `[spatial]` extra is not installed.
        KeyError: if the location, its boundaries, or its raster cannot be found.

    Example:
        >>> import starsim_data as ssd
        >>> nodes = ssd.fetch_nodes('kenya', level=1)   # doctest: +SKIP
    """
    verbose = sc.ifelse(verbose, ssd.options.verbose)
    year = _default_year() if year is None else int(year)
    level = ssd.parse_level(level)
    bundled = level in ssd.registry.dataset('nodes').levels

    # Default to the boundary source of the bundled node table, so the p-codes line up; at a
    # level that is not bundled, the source the country uses at level 1, if it has this level too
    if bundled:
        nodes = ssd.load_nodes(location, level=level)
        source = source or nodes.source.iloc[0]
    else:
        source = source or ssd.load_nodes(location, level=1).source.iloc[0]

    kwargs = dict(level=level, refresh=refresh, verbose=verbose)
    try:
        shapes = ssd.fetch_shapes(location, source=source, **kwargs)
    except KeyError:
        if bundled:
            raise
        shapes = ssd.fetch_shapes(location, **kwargs) # Not bundled: any source that has this level
        source = shapes.source.iloc[0]
    if not bundled:
        nodes = _nodes_from_shapes(shapes)

    # Sum the raster inside each unit
    raster = fetch_raster(location, year=year, refresh=refresh, verbose=verbose)
    units = [str(i) for i in range(len(shapes))]
    totals = aggregate_raster(raster, shapes.assign(unit=units), by='unit', nearest=COAST_DISTANCE)
    out = nodes.copy()
    if bundled: # Join on p-code
        by_pcode = dict(zip(shapes.pcode, [totals.get(unit) for unit in units]))
        out['population'] = out.pcode.map(by_pcode).astype(float)
    else:
        out['population'] = [float(totals.get(unit, np.nan)) for unit in units]
    unmatched = int(out.population.isna().sum())
    if unmatched and verbose:
        print(f'Note: {unmatched} of {len(out)} nodes got no population; the node table and the {source} boundaries may have drifted apart')

    out.attrs['provenance'] = sc.objdict(
        dataset             = 'nodes',
        tier                = 1,
        location            = nodes.location.iloc[0],
        level               = level,
        boundary_source     = source,
        population_source   = f"WorldPop {_product(year)['name']}",
        population_year     = year,
        population_url      = WORLDPOP_URL,
        population_license  = WORLDPOP_LICENSE,
        population_citation = WORLDPOP_CITATION,
        note                = 'WorldPop constrained estimates are modeled and will not exactly match the UN WPP national total; rescale if your model needs them to.',
    )
    if not bundled:
        out.attrs['borders'] = ssd.shapes.borders(shapes)
    return out


def _nodes_from_shapes(shapes):
    """A node table, as the bundled one is built, from the polygons of one level."""
    lat, lon, area = ssd.shapes.measure(shapes)
    out = sc.dataframe(shapes.drop(columns='geometry').reset_index(drop=True))
    out['parent']     = out['location']
    out['lat']        = lat
    out['lon']        = lon
    out['area_km2']   = area
    out['population'] = np.nan
    cols = ['nodeid', 'location', 'iso3', 'level', 'name', 'pcode', 'dot_name', 'parent', 'lat', 'lon', 'area_km2', 'population', 'source']
    return out[cols]


def rescale_to_national(nodes, location=None, year=None):
    """
    Scale node populations so they sum to this package's national WPP total.

    WorldPop and UN WPP disagree by a percent or two, and which one is "right" depends on
    the question. This makes the choice explicit rather than leaving two national totals
    silently in play.

    Args:
        nodes (dataframe): a node table with `population` filled, from `fetch_nodes()`.
        location (str): the location; taken from the table if not given.
        year (int): the WPP year to match; taken from the table's provenance if not given.

    Returns:
        sciris.dataframe: a copy with `population` rescaled.

    Example:
        >>> import starsim_data as ssd
        >>> nodes = ssd.rescale_to_national(ssd.fetch_nodes('kenya'))   # doctest: +SKIP
    """
    location = location or nodes.location.iloc[0]
    year = year or nodes.attrs.get('provenance', {}).get('population_year')
    population = ssd.load(location, which='population')
    years = np.asarray(sorted(set(population.Time)))
    if (year is None) or (year not in set(population.Time)): # WPP is decadal when bundled; take the nearest year
        target = year or years[-1]
        year = int(years[np.argmin(np.abs(years - target))])
    population = population[population.Time == year]

    total = float(population.Value.sum())
    out = nodes.copy()
    out['population'] = out.population * (total / out.population.sum())
    out.attrs['provenance'] = sc.objdict(nodes.attrs.get('provenance', {}))
    out.attrs['provenance'].rescaled_to = f'UN WPP national total for {year}'
    return out
