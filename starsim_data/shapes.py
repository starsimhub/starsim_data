"""
Administrative boundaries: the full geometry.

`load_nodes()` gives you centroids, areas and p-codes, which is what a metapopulation
model actually consumes and which fits in the wheel. This module gives you the polygons,
for maps, exact spatial joins and raster aggregation. Polygons do not fit in a wheel --
a single country at admin 2 runs to tens of MB -- so they are downloaded and cached, and
they need the optional geospatial stack:

```bash
pip install starsim_data[spatial]
```

```python
import starsim_data as ssd
ssd.list_shape_sources()                              # what's available, and its license
gdf = ssd.download_shapes('kenya', level=1)              # 47 counties, with geometry
gdf = ssd.download_shapes('kenya', level=2, source='gadm')
```

Three sources, because coverage genuinely varies by country and level:

| source | coverage | levels | key | license |
|---|---|---|---|---|
| `unocha` | ~110 countries | 0-4 | **p-code** | CC BY 3.0 IGO |
| `geoboundaries` | near-universal | 0-5 | `shapeID` | CC BY 4.0 |
| `gadm` | universal | 0-5 | `GID_n` | **non-commercial only** |

`source=None` tries UNOCHA then geoBoundaries -- UNOCHA first because its p-codes are
the join key for essentially all subnational health data. GADM is never reached
automatically: it is licensed for non-commercial use only, so asking for it has to be a
deliberate act. That constraint lives in the source descriptor
(`ShapeSource.redistributable`) rather than in anyone's memory, and the build scripts
refuse to derive bundled data from a source that sets it False.

Two things deliberately not ported from `laser-init`. Its UNOCHA extractor falls back to
a 1-2 GB global geodatabase when a country is missing; a download that size triggered
implicitly by a library call is user-hostile, and geoBoundaries covers the same gap for a
few MB. And its transformer writes GeoPackages to an output directory as a pipeline step;
here `download_shapes()` just returns the frame, and saving is `gdf.to_file(...)`.
"""

import zipfile
import warnings
import dataclasses as dc
import numpy as np
import zstandard
import sciris as sc
import starsim_data as ssd

__all__ = ['download_shapes', 'list_shape_sources', 'measure', 'borders']


@dc.dataclass(frozen=True)
class ShapeSource:
    """One administrative-boundary source, and the terms it comes on.

    Attributes:
        name (str): the key passed as `source=`.
        url (str): download template, with `{iso3}` and `{level}`.
        filename (str): cache filename template, with `{iso3}` and `{level}`.
        max_level (int): the finest administrative level published.
        license (str): the upstream license.
        redistributable (bool): whether derived data may be shipped inside this package.
            False for GADM, which is non-commercial only -- so it can be downloaded at
            runtime by a user who accepts those terms, but never bundled or released.
        universal (bool): whether coverage is effectively global (used for the fallback
            chain: a non-universal source is tried first but expected to miss).
    """
    name: str
    url: str
    filename: str
    max_level: int
    license: str
    source_url: str
    citation: str
    redistributable: bool = True
    universal: bool = False
    note: str = ''


GEOBOUNDARIES_TAG = 'v6.0.0' # Pinned: geoBoundaries' main branch moves under you

SOURCES = sc.objdict(
    unocha = ShapeSource(
        name       = 'unocha',
        url        = 'https://github.com/laser-base/unocha/raw/refs/heads/main/data/{iso3}/UNOCHA-{iso3}-ADM{level}.gpkg.zstd',
        filename   = 'UNOCHA-{iso3}-ADM{level}.gpkg.zstd',
        max_level  = 4,
        license    = 'CC BY 3.0 IGO',
        source_url = 'https://github.com/laser-base/unocha',
        citation   = 'United Nations Office for the Coordination of Humanitarian Affairs (UNOCHA), Common Operational Datasets - Administrative Boundaries (COD-AB).',
        note       = 'Carries p-codes and dot_names. Covers roughly 110 countries, weighted towards those with humanitarian operations.',
    ),
    geoboundaries = ShapeSource(
        name       = 'geoboundaries',
        url        = f'https://github.com/wmgeolab/geoBoundaries/raw/refs/tags/{GEOBOUNDARIES_TAG}/releaseData/gbOpen/{{iso3}}/ADM{{level}}/geoBoundaries-{{iso3}}-ADM{{level}}-all.zip',
        filename   = 'geoBoundaries-{iso3}-ADM{level}.zip',
        max_level  = 5,
        license    = 'CC BY 4.0',
        source_url = 'https://www.geoboundaries.org',
        citation   = 'Runfola D, Anderson A, Baier H, et al. (2020). geoBoundaries: A global database of political administrative boundaries. PLoS ONE 15(4): e0231866.',
        universal  = True,
        note       = f'Pinned to {GEOBOUNDARIES_TAG} for reproducibility. Identifiers are geoBoundaries shapeIDs, not p-codes.',
    ),
    gadm = ShapeSource(
        name            = 'gadm',
        url             = 'https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_{iso3}.gpkg',
        filename        = 'gadm41_{iso3}.gpkg',
        max_level       = 5,
        license         = 'Non-commercial use only',
        source_url      = 'https://gadm.org',
        citation        = 'GADM: Database of Global Administrative Areas, version 4.1.',
        redistributable = False,
        universal       = True,
        note            = 'NON-COMMERCIAL ONLY. Never reached by the automatic fallback, never bundled, never redistributed -- download at runtime or not at all. One file per country containing every level (~50 MB).',
    ),
)

# Tried in order when `source=None`. GADM is absent by design: see the module docstring.
FALLBACK_CHAIN = ('unocha', 'geoboundaries')

# The columns every source is normalized onto, so that a caller does not have to know
# which one answered.
COLUMNS = ('nodeid', 'location', 'iso3', 'level', 'name', 'pcode', 'dot_name', 'source', 'geometry')


def _require_spatial(what):
    """Import geopandas, or explain how to get it."""
    try:
        import geopandas as gpd # Imported here since it is optional (the [spatial] extra), and `import starsim_data` must work without it
    except ImportError as e:
        raise ImportError(f'{what} needs the optional geospatial dependencies; install them with: pip install starsim_data[spatial]') from e
    return gpd


def list_shape_sources():
    """Return the boundary sources as a dataframe: coverage, levels and license.

    Returns:
        sciris.dataframe: with columns `[source, max_level, license, redistributable,
        universal, note]`.

    Example:
        ```python
        import starsim_data as ssd
        ssd.list_shape_sources() # One row per source; GADM's has redistributable=False
        ```
    """
    rows = []
    for s in SOURCES.values():
        rows.append(dict(source=s.name, max_level=s.max_level, license=s.license, redistributable=s.redistributable, universal=s.universal, note=s.note))
    return sc.dataframe(rows)


def _read_unocha(path, iso3, level, gpd):
    """Read a zstd-compressed per-country GeoPackage from the UNOCHA mirror."""
    gpkg = path.with_suffix('') # Drop '.zstd'
    if not gpkg.exists():
        with open(path, 'rb') as fi, open(gpkg, 'wb') as fo:
            zstandard.ZstdDecompressor().copy_stream(fi, fo)
    gdf = gpd.read_file(gpkg, layer=f'UNOCHA-{iso3}-ADM{level}')
    return gdf.rename(columns={f'adm{level}_name': 'name', f'adm{level}_pcode': 'pcode'})


def _read_geoboundaries(path, iso3, level, gpd):
    """Read the GeoJSON out of a geoBoundaries `-all.zip` bundle.

    The bundle holds the same boundaries as shapefile, GeoJSON and TopoJSON at a couple
    of simplifications; take the unsimplified GeoJSON, since a simplified outline would
    quietly change any area or raster aggregation computed from it.
    """
    with zipfile.ZipFile(path) as z:
        contents = z.namelist()
    names = [n for n in contents if n.endswith('.geojson') and ('simplified' not in n.lower())]
    if not names:
        raise FileNotFoundError(f'no unsimplified GeoJSON inside {path.name}: {contents}')
    gdf = gpd.read_file(f'zip://{path}!{names[0]}')
    return gdf.rename(columns={'shapeName': 'name', 'shapeID': 'pcode'})


def _read_gadm(path, iso3, level, gpd):
    """Read one level out of a GADM per-country GeoPackage (all levels in one file)."""
    gdf = gpd.read_file(path, layer=f'ADM_ADM_{level}')
    name_col  = 'COUNTRY' if level == 0 else f'NAME_{level}'
    pcode_col = 'GID_0'   if level == 0 else f'GID_{level}'
    return gdf.rename(columns={name_col: 'name', pcode_col: 'pcode'})


READERS = dict(
    unocha        = _read_unocha,
    geoboundaries = _read_geoboundaries,
    gadm          = _read_gadm,
)


def _normalize(gdf, location, iso3, level, source):
    """Trim a source's frame to the shared schema, matching the node table's spelling."""
    out = gdf.copy()
    out['location'] = location
    out['iso3']     = iso3
    out['level']    = level
    out['source']   = source
    out['name']     = out['name'].astype(str)
    out['pcode']    = out['pcode'].astype(str)
    out['dot_name'] = [location if level == 0 else f'{location}:{ssd.node_name(n)}' for n in out['name']]
    out['nodeid']   = range(len(out))
    return out[[c for c in COLUMNS if c in out.columns]]


def download_shapes(location, level=1, source=None, refresh=False, verbose=None):
    """
    Download administrative boundaries with full geometry from their publisher, and cache them.

    Requires the `[spatial]` extra. For centroids, areas and populations without any
    geospatial dependency, use `load_nodes()` instead -- it is bundled and instant.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        level (int/str): administrative level; 0 is the country, 1 its first-level
            subdivisions. Accepts `'admin2'` / `'ADM2'` / `2`.
        source (str): `'unocha'`, `'geoboundaries'` or `'gadm'`. None (default) tries
            UNOCHA then geoBoundaries. GADM is never tried automatically -- it is
            licensed for non-commercial use only, so it must be asked for by name.
        refresh (bool): re-download even if the file is already cached.
        verbose (bool): report progress (default: `options.verbose`).

    Returns:
        geopandas.GeoDataFrame: columns `nodeid`, `location`, `iso3`, `level`, `name`,
        `pcode`, `dot_name`, `source`, `geometry`. `pcode` and `dot_name` match
        `load_nodes()` for the same source, so the two join directly.

    Raises:
        ImportError: if the `[spatial]` extra is not installed.
        ValueError: if the source or level is not recognized.
        KeyError: if the location is unknown, or no source has it at this level.

    Example:
        ```python
        import starsim_data as ssd
        gdf = ssd.download_shapes('kenya', level=1)
        ```
    """
    gpd = _require_spatial('download_shapes()')
    verbose = sc.ifelse(verbose, ssd.options.verbose)
    level = ssd.parse_level(level)
    key = ssd.resolve(location)
    iso3 = ssd.location_info(key).iso3

    if (source is not None) and (source not in SOURCES):
        raise ValueError(f'unknown shape source {source!r}; available: {list(SOURCES)}')
    wanted = [source] if source else list(FALLBACK_CHAIN)

    # Try each source in turn, returning the first that has this location at this level
    problems = []
    for name in wanted:
        spec = SOURCES[name]
        if level > spec.max_level:
            problems.append(f'{name}: publishes up to level {spec.max_level}')
            continue
        if (not spec.redistributable) and verbose:
            print(f'Note: {name} is licensed for {spec.license.lower()}; the data you download must not be redistributed.')
        url      = spec.url.format(iso3=iso3, level=level)
        filename = spec.filename.format(iso3=iso3, level=level)
        try:
            path = ssd.cached_download(url, filename=filename, subdir='boundaries', refresh=refresh, verbose=verbose)
            gdf = READERS[name](path, iso3, level, gpd)
        except Exception as e: # Any failure means try the next source
            problems.append(f'{name}: {e}')
            continue
        out = _normalize(gdf, key, iso3, level, name)
        out.attrs['provenance'] = sc.objdict(
            dataset         = 'shapes',
            source          = name,
            tier            = 2,
            source_url      = spec.source_url,
            license         = spec.license,
            citation        = spec.citation,
            redistributable = spec.redistributable,
            location        = key,
            iso3            = iso3,
            level           = level,
        )
        return out

    detail = '; '.join(problems)
    raise KeyError(f'no boundaries for {key} ({iso3}) at level {level} from {wanted} ({detail})')



def fetch_shapes(location, level=1, source=None, refresh=False, verbose=None):
    """Not packaged: warns that the boundaries come from an external source, then calls `download_shapes()`."""
    ssd.downloading._external('Administrative boundaries', 'UNOCHA, geoBoundaries or GADM', 'download_shapes()')
    return download_shapes(location, level=level, source=source, refresh=refresh, verbose=verbose)

# Centroids are taken in an equal-area projection and converted back: the centroid of a
# polygon in raw degrees is pulled poleward and is simply the wrong point.
EQUAL_AREA = 'ESRI:54009' # Mollweide
TOUCH_TOLERANCE = 1e-3    # Degrees (~100 m): units closer than this share a border, which absorbs slivers between polygons


def measure(gdf):
    """
    The centroid latitude and longitude, and the area in km², of each polygon.

    Args:
        gdf (GeoDataFrame): polygons in WGS84, e.g. from `download_shapes()`.

    Returns:
        tuple: arrays of latitudes, longitudes and areas, one entry per row.
    """
    from pyproj import Geod # Imported here since it is optional (it comes with the [spatial] extra)

    geod = Geod(ellps='WGS84')
    areas = np.array([abs(geod.geometry_area_perimeter(g)[0]) / 1e6 for g in gdf.geometry]) # Geodesic area, m² -> km²
    centroids = gdf.to_crs(EQUAL_AREA).centroid.to_crs('EPSG:4326')
    lat = centroids.y.to_numpy()
    lon = centroids.x.to_numpy()
    return lat, lon, areas


def borders(gdf, tolerance=TOUCH_TOLERANCE):
    """
    The pairs of polygons that share a border.

    Args:
        gdf (GeoDataFrame): polygons in WGS84, e.g. from `download_shapes()`.
        tolerance (float): polygons closer than this, in degrees, count as touching
            (default about 100 m, which absorbs slivers between neighboring polygons).

    Returns:
        numpy.ndarray: `(n, 2)` row positions `(i, j)` with `i < j`.
    """
    with warnings.catch_warnings(): # A buffer in degrees is what is meant here, so geopandas' warning about it does not apply
        warnings.simplefilter('ignore', UserWarning)
        geoms = gdf.geometry.reset_index(drop=True).buffer(tolerance / 2)
    i, j = geoms.sindex.query(geoms, predicate='intersects')
    keep = i < j # Each pair once, and not a polygon with itself
    return np.stack([i[keep], j[keep]], axis=1).astype(np.int32)
