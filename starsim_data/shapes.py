"""
Administrative boundaries: the full geometry.

`load_nodes()` gives you centroids, areas and p-codes, which is what a metapopulation
model actually consumes and which fits in the wheel. This module gives you the polygons,
for maps, exact spatial joins and raster aggregation. Polygons do not fit in a wheel --
a single country at admin 2 runs to tens of MB -- so they are fetched and cached, and
they need the optional geospatial stack:

```bash
pip install starsim_data[spatial]
```

```python
import starsim_data as ssd
ssd.list_shape_sources()                              # what's available, and its license
gdf = ssd.fetch_shapes('kenya', level=1)              # 47 counties, with geometry
gdf = ssd.fetch_shapes('kenya', level=2, source='gadm')
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
here `fetch_shapes()` just returns the frame, and saving is `gdf.to_file(...)`.
"""

import zipfile
from dataclasses import dataclass

import sciris as sc
import starsim_data as ssd

__all__ = ["fetch_shapes", "list_shape_sources"]


@dataclass(frozen=True)
class ShapeSource:
    """One administrative-boundary source, and the terms it comes on.

    Attributes:
        name (str): the key passed as `source=`.
        url (str): download template, with `{iso3}` and `{level}`.
        filename (str): cache filename template, with `{iso3}` and `{level}`.
        max_level (int): the finest administrative level published.
        license (str): the upstream license.
        redistributable (bool): whether derived data may be shipped inside this package.
            False for GADM, which is non-commercial only -- so it can be fetched at
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
    note: str = ""


GEOBOUNDARIES_TAG = "v6.0.0"   # pinned: geoBoundaries' main branch moves under you

SOURCES = sc.objdict(
    unocha=ShapeSource(
        name="unocha",
        url=("https://github.com/laser-base/unocha/raw/refs/heads/main/data/"
             "{iso3}/UNOCHA-{iso3}-ADM{level}.gpkg.zstd"),
        filename="UNOCHA-{iso3}-ADM{level}.gpkg.zstd",
        max_level=4,
        license="CC BY 3.0 IGO",
        source_url="https://github.com/laser-base/unocha",
        citation="United Nations Office for the Coordination of Humanitarian Affairs "
                 "(UNOCHA), Common Operational Datasets - Administrative Boundaries (COD-AB).",
        note="Carries p-codes and dot_names. Covers roughly 110 countries, weighted "
             "towards those with humanitarian operations."),
    geoboundaries=ShapeSource(
        name="geoboundaries",
        url=("https://github.com/wmgeolab/geoBoundaries/raw/refs/tags/" + GEOBOUNDARIES_TAG +
             "/releaseData/gbOpen/{iso3}/ADM{level}/geoBoundaries-{iso3}-ADM{level}-all.zip"),
        filename="geoBoundaries-{iso3}-ADM{level}.zip",
        max_level=5,
        license="CC BY 4.0",
        source_url="https://www.geoboundaries.org",
        citation="Runfola D, Anderson A, Baier H, et al. (2020). geoBoundaries: A global "
                 "database of political administrative boundaries. PLoS ONE 15(4): e0231866.",
        universal=True,
        note=f"Pinned to {GEOBOUNDARIES_TAG} for reproducibility. Identifiers are "
             f"geoBoundaries shapeIDs, not p-codes."),
    gadm=ShapeSource(
        name="gadm",
        url="https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_{iso3}.gpkg",
        filename="gadm41_{iso3}.gpkg",
        max_level=5,
        license="Non-commercial use only",
        source_url="https://gadm.org",
        citation="GADM: Database of Global Administrative Areas, version 4.1.",
        redistributable=False,
        universal=True,
        note="NON-COMMERCIAL ONLY. Never reached by the automatic fallback, never "
             "bundled, never redistributed -- fetch at runtime or not at all. One file "
             "per country containing every level (~50 MB)."),
)

# Tried in order when `source=None`. GADM is absent by design: see the module docstring.
FALLBACK_CHAIN = ("unocha", "geoboundaries")

# The columns every source is normalized onto, so that a caller does not have to know
# which one answered.
COLUMNS = ("nodeid", "location", "iso3", "level", "name", "pcode", "dot_name", "source",
           "geometry")


def _require_spatial(what):
    """Import geopandas, or explain how to get it."""
    try:
        import geopandas as gpd       # pylint: disable=import-outside-toplevel
    except ImportError as e:
        raise ImportError(f"{what} needs the optional geospatial dependencies; install "
                          f"them with: pip install starsim_data[spatial]") from e
    return gpd


def list_shape_sources():
    """Return the boundary sources as a dataframe: coverage, levels and license.

    Returns:
        sciris.dataframe: with columns `[source, max_level, license, redistributable,
        universal, note]`.

    Example:
        >>> import starsim_data as ssd
        >>> bool(ssd.list_shape_sources().set_index('source').loc['gadm', 'redistributable'])
        False
    """
    return sc.dataframe([dict(source=s.name, max_level=s.max_level, license=s.license,
                              redistributable=s.redistributable, universal=s.universal,
                              note=s.note) for s in SOURCES.values()])


def _read_unocha(path, iso3, level, gpd):
    """Read a zstd-compressed per-country GeoPackage from the UNOCHA mirror."""
    import zstandard      # pylint: disable=import-outside-toplevel  # (arrives with sciris)

    gpkg = path.with_suffix("")           # drop '.zstd'
    if not gpkg.exists():
        with path.open("rb") as fi, gpkg.open("wb") as fo:
            zstandard.ZstdDecompressor().copy_stream(fi, fo)
    gdf = gpd.read_file(gpkg, layer=f"UNOCHA-{iso3}-ADM{level}")
    return gdf.rename(columns={f"adm{level}_name": "name", f"adm{level}_pcode": "pcode"})


def _read_geoboundaries(path, iso3, level, gpd):
    """Read the GeoJSON out of a geoBoundaries `-all.zip` bundle.

    The bundle holds the same boundaries as shapefile, GeoJSON and TopoJSON at a couple
    of simplifications; take the unsimplified GeoJSON, since a simplified outline would
    quietly change any area or raster aggregation computed from it.
    """
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist()
                 if n.endswith(".geojson") and "simplified" not in n.lower()]
        if not names:
            raise FileNotFoundError(f"no unsimplified GeoJSON inside {path.name}: "
                                    f"{z.namelist()}")
    gdf = gpd.read_file(f"zip://{path}!{names[0]}")
    return gdf.rename(columns={"shapeName": "name", "shapeID": "pcode"})


def _read_gadm(path, iso3, level, gpd):
    """Read one level out of a GADM per-country GeoPackage (all levels in one file)."""
    gdf = gpd.read_file(path, layer=f"ADM_ADM_{level}")
    name_col = "COUNTRY" if level == 0 else f"NAME_{level}"
    pcode_col = "GID_0" if level == 0 else f"GID_{level}"
    return gdf.rename(columns={name_col: "name", pcode_col: "pcode"})


READERS = dict(unocha=_read_unocha, geoboundaries=_read_geoboundaries, gadm=_read_gadm)


def _normalize(gdf, location, iso3, level, source):
    """Trim a source's frame to the shared schema, matching the node table's spelling."""
    out = gdf.copy()
    out["location"] = location
    out["iso3"] = iso3
    out["level"] = level
    out["source"] = source
    out["name"] = out["name"].astype(str)
    out["pcode"] = out["pcode"].astype(str)
    out["dot_name"] = [location if level == 0 else f"{location}:{ssd.node_name(n)}"
                       for n in out["name"]]
    out["nodeid"] = range(len(out))
    return out[[c for c in COLUMNS if c in out.columns]]


def fetch_shapes(location, level=1, source=None, refresh=False, verbose=None):
    """
    Fetch administrative boundaries with full geometry, downloading and caching as needed.

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
        >>> import starsim_data as ssd
        >>> gdf = ssd.fetch_shapes('kenya', level=1)   # doctest: +SKIP
    """
    gpd = _require_spatial("fetch_shapes()")
    verbose = ssd.options.verbose if verbose is None else verbose
    level = ssd.parse_level(level)
    key = ssd.resolve(location)
    iso3 = ssd.location_info(key).iso3

    if source is not None and source not in SOURCES:
        raise ValueError(f"unknown shape source {source!r}; available: {list(SOURCES)}")
    wanted = [source] if source else list(FALLBACK_CHAIN)

    problems = []
    for name in wanted:
        spec = SOURCES[name]
        if level > spec.max_level:
            problems.append(f"{name}: publishes up to level {spec.max_level}")
            continue
        if not spec.redistributable and verbose:
            print(f"Note: {name} is licensed for {spec.license.lower()}; the data you "
                  f"fetch must not be redistributed.")
        try:
            path = ssd.cached_download(spec.url.format(iso3=iso3, level=level),
                                       filename=spec.filename.format(iso3=iso3, level=level),
                                       subdir="boundaries", refresh=refresh, verbose=verbose)
            gdf = READERS[name](path, iso3, level, gpd)
        except Exception as e:      # noqa: BLE001 -- any failure means try the next source
            problems.append(f"{name}: {e}")
            continue
        out = _normalize(gdf, key, iso3, level, name)
        out.attrs["provenance"] = sc.objdict(dataset="shapes", source=name, tier=1,
                                             source_url=spec.source_url,
                                             license=spec.license, citation=spec.citation,
                                             redistributable=spec.redistributable,
                                             location=key, iso3=iso3, level=level)
        return out

    detail = "; ".join(problems)
    raise KeyError(f"no boundaries for {key} ({iso3}) at level {level} from "
                   f"{wanted} ({detail})")
