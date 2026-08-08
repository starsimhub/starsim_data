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

A caution worth carrying: WorldPop's *constrained* estimates are modelled, not counted,
and they will not equal the UN WPP national total for the same year -- for Kenya 2020
they come out about 1% low. If a model needs the national total to match WPP exactly,
rescale: `nodes.population *= wpp_total / nodes.population.sum()`.
"""

import contextlib
import io
import tempfile
from pathlib import Path

import numpy as np
import sciris as sc
import starsim_data as ssd

__all__ = ["fetch_nodes", "fetch_raster", "aggregate_raster", "rescale_to_national"]

WORLDPOP_LICENSE = "CC BY 4.0"
WORLDPOP_URL = "https://www.worldpop.org"
WORLDPOP_CITATION = ("WorldPop (www.worldpop.org), School of Geography and Environmental "
                     "Science, University of Southampton. https://dx.doi.org/10.5258/SOTON/WP00645")

# WorldPop publishes two 1 km products over different year ranges, with different naming.
# The newer one is UN-adjusted and constrained to built settlement; the older is the
# UN-adjusted unconstrained series.
PRODUCTS = (
    dict(first=2015, last=2030,
         url=("https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/"
              "{iso3}/v1/1km_ua/constrained/{lower}_pop_{year}_CN_1km_R2025A_UA_v1.tif"),
         name="Global_2015_2030 R2025A, 1 km, constrained, UN-adjusted"),
    dict(first=2000, last=2020,
         url=("https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/"
              "{year}/{iso3}/{lower}_ppp_{year}_1km_Aggregated_UNadj.tif"),
         name="Global_2000_2020, 1 km, UN-adjusted"),
)


def _product(year):
    """Return the WorldPop product covering `year`, preferring the newer series."""
    for product in PRODUCTS:
        if product["first"] <= year <= product["last"]:
            return product
    first = min(p["first"] for p in PRODUCTS)
    last = max(p["last"] for p in PRODUCTS)
    raise ValueError(f"WorldPop 1 km population is published for {first}-{last}, not {year}")


def _default_year():
    """The year the bundled node table uses for national population, so the two agree."""
    return int(ssd.provenance("nodes").get("population_year", 2020))


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
    verbose = ssd.options.verbose if verbose is None else verbose
    year = _default_year() if year is None else int(year)
    product = _product(year)
    key = ssd.resolve(location)
    iso3 = ssd.location_info(key).iso3

    url = product["url"].format(year=year, iso3=iso3, lower=iso3.lower())
    try:
        path = Path(ssd.cached_download(url, filename=f"worldpop_{iso3}_{year}.tif",
                                        subdir="worldpop", refresh=refresh, verbose=verbose))
    except Exception as e:      # noqa: BLE001 -- an HTTP failure means "not published"
        raise KeyError(f"WorldPop has no {year} raster for {key} ({iso3}): {e}") from e
    # Small territories 404 into a zero-length file rather than an error; catch that here
    # instead of letting it surface as an inscrutable raster-reading failure.
    if path.stat().st_size == 0:
        path.unlink()
        raise KeyError(f"WorldPop's {year} raster for {key} ({iso3}) is empty; the 1 km "
                       f"series does not cover every small territory")
    return path


def aggregate_raster(raster, shapes, by="pcode"):
    """
    Sum a raster inside each polygon: zonal statistics, keyed by an attribute.

    Args:
        raster (str/Path): a GeoTIFF, e.g. from `fetch_raster()`.
        shapes (GeoDataFrame): polygons, e.g. from `fetch_shapes()`.
        by (str): the column of `shapes` to key the result on.

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
        import rastertoolkit as rtk      # pylint: disable=import-outside-toplevel
    except ImportError as e:
        raise ImportError("aggregate_raster() needs the optional geospatial dependencies; "
                          "install them with: pip install starsim_data[spatial]") from e
    if by not in shapes.columns:
        raise ValueError(f"{by!r} is not a column of the shapes; available: "
                         f"{list(shapes.columns)}")

    # rastertoolkit reads shapes with pyshp, so it wants a shapefile on disk rather than a
    # GeoDataFrame in memory.
    with tempfile.TemporaryDirectory() as tmp:
        stem = Path(tmp) / "shapes"
        shapes[[by, "geometry"]].to_file(stem.with_suffix(".shp"), driver="ESRI Shapefile")
        with contextlib.redirect_stdout(io.StringIO()):     # it prints per-shape progress
            return rtk.raster_clip(str(raster), str(stem), shape_attr=by, quiet=True)


def fetch_nodes(location, level=1, year=None, source=None, refresh=False, verbose=None):
    """
    The node table with `population` filled in, from WorldPop.

    `load_nodes()` is instant and offline but only knows national population.
    This downloads the boundaries and the population raster for a country, sums the
    raster inside each unit, and returns the same table with the numbers filled in.

    The boundaries are fetched from whichever source the bundled node table used for this
    country, so the p-codes line up and the join is exact rather than by name.

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
    verbose = ssd.options.verbose if verbose is None else verbose
    year = _default_year() if year is None else int(year)
    nodes = ssd.load_nodes(location, level=level)
    source = source or nodes.source.iloc[0]

    shapes = ssd.fetch_shapes(location, level=level, source=source, refresh=refresh,
                              verbose=verbose)
    raster = fetch_raster(location, year=year, refresh=refresh, verbose=verbose)
    totals = aggregate_raster(raster, shapes, by="pcode")

    out = nodes.copy()
    out["population"] = out.pcode.map(totals).astype(float)
    unmatched = int(out.population.isna().sum())
    if unmatched and verbose:
        print(f"Note: {unmatched} of {len(out)} nodes got no population; the node table "
              f"and the {source} boundaries may have drifted apart")

    out.attrs["provenance"] = sc.objdict(
        dataset="nodes", tier=1, location=nodes.location.iloc[0], level=level,
        boundary_source=source,
        population_source=f"WorldPop {_product(year)['name']}",
        population_year=year, population_url=WORLDPOP_URL,
        population_license=WORLDPOP_LICENSE, population_citation=WORLDPOP_CITATION,
        note="WorldPop constrained estimates are modelled and will not exactly match the "
             "UN WPP national total; rescale if your model needs them to.")
    return out


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
    year = year or nodes.attrs.get("provenance", {}).get("population_year")
    population = ssd.load(location, which="population")
    if year is not None and year in set(population.Time):
        population = population[population.Time == year]
    else:                       # WPP is decadal when bundled; take the nearest year
        years = np.asarray(sorted(set(population.Time)))
        nearest = int(years[np.argmin(np.abs(years - (year or years[-1])))])
        population = population[population.Time == nearest]
        year = nearest

    total = float(population.Value.sum())
    out = nodes.copy()
    out["population"] = out.population * (total / out.population.sum())
    out.attrs["provenance"] = sc.objdict(nodes.attrs.get("provenance", {}))
    out.attrs["provenance"].rescaled_to = f"UN WPP national total for {year}"
    return out
