"""
Build the node table: `starsim_data/data/nodes.h5`.

Dev/CI tool -- NOT part of the installed package.

A *node table* is the lightweight half of a metapopulation input. A spatial model mostly
needs to know, for each administrative unit, where it is, how big it is and how many
people live there -- not the exact shape of its border. Reduced to centroids, areas and
p-codes, the whole world at admin 0 and 1 is a few hundred KB and needs no geospatial
libraries to read, so it bundles inside the wheel. Full geometry stays a fetch (see
`starsim_data.shapes`), because it does not.

Two boundary sources, in preference order per country:

1. **UNOCHA COD-AB**, via the per-country GeoPackages at https://github.com/laser-base/unocha.
   Preferred because it carries **p-codes** -- the join key for essentially all
   subnational humanitarian and health data. Covers ~110 countries.
2. **geoBoundaries CGAZ v6.0.0**, two global GeoPackages. Near-universal coverage, but
   its `shapeID` is a geoBoundaries identifier rather than a p-code.

Each row records which source it came from, because the two do not always agree on how a
country subdivides, and a silent mix would be worse than a labelled one.

Population is filled at level 0 only, from this package's own bundled UN WPP data. It is
deliberately *not* filled at level 1: that needs WorldPop raster aggregation, which is a
~1 GB scrape of a slow server with real coverage gaps, and belongs at fetch time rather
than in the wheel. See `starsim_data.rasters` and `fetch_nodes(population=True)`.

Usage:

```bash
python scripts/build_nodes.py            # -> starsim_data/data/nodes.h5
python scripts/build_nodes.py --check    # rebuild and validate via the loader
python scripts/build_nodes.py --limit 5  # a quick subset, for development
```
"""

import argparse
import json
import sys
import urllib.request
import warnings
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from provenance import stamp

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "starsim_data" / "data"
LOCATIONS_CSV = OUT / "locations.csv"

sys.path.insert(0, str(REPO))
import starsim_data as ssd  # noqa: E402 -- needs the sys.path line above

# --- Sources ------------------------------------------------------------------------ #

CGAZ_TAG = "v6.0.0"      # pinned: geoBoundaries' main branch moves
CGAZ_URL = ("https://github.com/wmgeolab/geoBoundaries/raw/refs/tags/" + CGAZ_TAG +
            "/releaseData/CGAZ/geoBoundariesCGAZ_ADM{level}.gpkg")
UNOCHA_TREE = "https://api.github.com/repos/laser-base/unocha/git/trees/main?recursive=1"
UNOCHA_URL = ("https://github.com/laser-base/unocha/raw/refs/heads/main/data/"
              "{iso3}/UNOCHA-{iso3}-ADM{level}.gpkg.zstd")

SOURCES = {
    "unocha": dict(
        source="UNOCHA Common Operational Datasets (COD-AB), via the laser-base mirror",
        source_url="https://github.com/laser-base/unocha",
        license="CC BY 3.0 IGO",
        citation="United Nations Office for the Coordination of Humanitarian Affairs (UNOCHA), "
                 "Common Operational Datasets - Administrative Boundaries (COD-AB)."),
    "geoboundaries": dict(
        source=f"geoBoundaries CGAZ {CGAZ_TAG} (gbOpen)",
        source_url="https://www.geoboundaries.org",
        license="CC BY 4.0",
        citation="Runfola D, Anderson A, Baier H, et al. (2020). geoBoundaries: A global "
                 "database of political administrative boundaries. PLoS ONE 15(4): e0231866."),
}

LEVELS = (0, 1)

# Columns of the node table, in order. Kept in step with `starsim_data/nodes.py`.
COLUMNS = ("nodeid", "location", "iso3", "level", "name", "pcode", "dot_name", "parent",
           "lat", "lon", "area_km2", "population", "source")
STR_COLS = ("location", "iso3", "name", "pcode", "dot_name", "parent", "source")

# Centroids are taken in an equal-area projection and converted back: the centroid of a
# polygon in raw degrees is pulled poleward and is simply the wrong point.
EQUAL_AREA = "ESRI:54009"      # Mollweide


def cache_path(url, name):
    """Download `url` into the package cache if it is not already there."""
    return ssd.cached_download(url, filename=name, subdir="boundaries")


def unocha_coverage():
    """Return `{iso3: {level}}` for what the UNOCHA mirror actually publishes."""
    with urllib.request.urlopen(UNOCHA_TREE, timeout=120) as r:
        tree = json.load(r)["tree"]
    coverage = {}
    for entry in tree:
        path = entry["path"]
        if not path.endswith(".gpkg.zstd"):
            continue
        iso3 = path.split("/")[1]
        level = int(path.rsplit("ADM", 1)[1].split(".")[0])
        coverage.setdefault(iso3, set()).add(level)
    return coverage


def read_unocha(iso3, level):
    """Read one UNOCHA per-country GeoPackage, decompressing it first."""
    import geopandas as gpd
    import zstandard

    name = f"UNOCHA-{iso3}-ADM{level}.gpkg.zstd"
    compressed = Path(cache_path(UNOCHA_URL.format(iso3=iso3, level=level), name))
    gpkg = compressed.with_suffix("")
    if not gpkg.exists():
        with compressed.open("rb") as fi, gpkg.open("wb") as fo:
            zstandard.ZstdDecompressor().copy_stream(fi, fo)
    gdf = gpd.read_file(gpkg, layer=f"UNOCHA-{iso3.upper()}-ADM{level}")
    return gdf.rename(columns={f"adm{level}_name": "name", f"adm{level}_pcode": "pcode"})


def read_cgaz(level):
    """Read one global geoBoundaries CGAZ layer, keyed by ISO-3 in `shapeGroup`."""
    import geopandas as gpd

    name = f"geoBoundariesCGAZ_ADM{level}.gpkg"
    gdf = gpd.read_file(cache_path(CGAZ_URL.format(level=level), name))
    # CGAZ ships without a declared CRS, but the coordinates are WGS84 lat/lon.
    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    gdf = gdf.rename(columns={"shapeName": "name", "shapeGroup": "iso3", "shapeID": "pcode"})
    if "pcode" not in gdf.columns:       # the ADM0 layer has no shapeID
        gdf["pcode"] = gdf["iso3"]
    return gdf


def geometry_facts(gdf):
    """Return centroid latitude/longitude and geodesic area in km2 for each feature."""
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    areas = np.array([abs(geod.geometry_area_perimeter(g)[0]) / 1e6 for g in gdf.geometry])
    centroids = gdf.to_crs(EQUAL_AREA).centroid.to_crs("EPSG:4326")
    return centroids.y.to_numpy(), centroids.x.to_numpy(), areas


def national_populations(year=None):
    """Return `{location: population}` from the bundled WPP data, for one year."""
    out, chosen = {}, year
    for location in ssd.list_locations("population"):
        df = ssd.load(location, which="population")
        if chosen is None:      # the most recent year that is an estimate, not a forecast
            chosen = int(max(y for y in df.Time.unique() if y <= pd.Timestamp.now().year))
        out[location] = float(df[df.Time == chosen].Value.sum())
    return out, chosen


def build_location(location, iso3, frames, populations):
    """Return the node rows for one location, across all levels.

    `nodeid` restarts at 0 for each level, so it indexes directly into the level's
    distance matrix -- node *i* of this metapopulation, not row *i* of the file.
    """
    rows = []
    for level in LEVELS:
        gdf, source = frames.get(level, (None, None))
        if gdf is None or not len(gdf):
            continue
        lat, lon, area = geometry_facts(gdf)
        for i in range(len(gdf)):
            name = str(gdf["name"].iloc[i])
            canonical = location if level == 0 else ssd.node_name(name)
            rows.append(dict(
                nodeid=i,
                location=location,
                iso3=iso3,
                level=level,
                name=name,
                pcode=str(gdf["pcode"].iloc[i]),
                dot_name=canonical if level == 0 else f"{location}:{canonical}",
                parent="" if level == 0 else location,
                lat=float(lat[i]),
                lon=float(lon[i]),
                area_km2=float(area[i]),
                population=populations.get(location, np.nan) if level == 0 else np.nan,
                source=source,
            ))
    return rows


def gather(location, iso3, coverage, cgaz):
    """Return `{level: (GeoDataFrame, source)}` for a location, preferring UNOCHA."""
    frames = {}
    for level in LEVELS:
        if level in coverage.get(iso3, set()):
            try:
                frames[level] = (read_unocha(iso3, level), "unocha")
                continue
            except Exception as e:      # noqa: BLE001 -- fall through to geoBoundaries
                print(f"    {iso3} ADM{level}: UNOCHA read failed ({e}); using geoBoundaries")
        subset = cgaz[level][cgaz[level].iso3 == iso3]
        if len(subset):
            frames[level] = (subset, "geoboundaries")
    return frames


def write(rows, out_path, population_year, verbose=True):
    """Write the node table, one compound dataset per location."""
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    dtype = np.dtype([(c, h5py.string_dtype()) if c in STR_COLS
                      else (c, np.int32) if c in ("nodeid", "level")
                      else (c, np.float64) for c in COLUMNS])

    with h5py.File(out_path, "w") as f:
        f.attrs["spec"] = json.dumps(dict(
            layout="nodes", levels=list(LEVELS), columns=list(COLUMNS),
            population_year=population_year,
            note="Centroids are equal-area centroids in WGS84; area_km2 is geodesic. "
                 "population is national (level 0) only -- see starsim_data.rasters "
                 "for subnational population."))
        f.attrs["provenance"] = json.dumps(stamp(
            "nodes", "scripts/build_nodes.py",
            source="; ".join(s["source"] for s in SOURCES.values()),
            source_url="; ".join(s["source_url"] for s in SOURCES.values()),
            license="; ".join(f"{k}: {v['license']}" for k, v in SOURCES.items()),
            citation=" | ".join(s["citation"] for s in SOURCES.values()),
            sources={k: v for k, v in SOURCES.items()},
            population_source="UN World Population Prospects, via this package",
            population_year=population_year))
        for location, group in df.groupby("location", sort=True):
            arr = np.zeros(len(group), dtype=dtype)
            for col in COLUMNS:
                arr[col] = group[col].to_numpy()
            f.create_dataset(location, data=arr, compression="gzip", compression_opts=9)

    if verbose:
        counts = df.groupby("level").size()
        print(f"  {out_path.name}: {out_path.stat().st_size/1e6:.2f} MB, "
              f"{len(df)} nodes across {df.location.nunique()} locations "
              f"({', '.join(f'level {k}: {v}' for k, v in counts.items())})")
        print(f"  sources: {dict(df.groupby('source').size())}")
    return df


def build(limit=None, check=False):
    """Build the node table from the boundary sources."""
    locations = pd.read_csv(LOCATIONS_CSV, keep_default_na=False, na_values=[])
    if limit:
        locations = locations.head(limit)

    # The bundled node table is derived data, so every source it draws on must permit
    # redistribution. GADM does not, which is why it is absent here as well as from the
    # automatic fallback chain in `starsim_data.shapes`.
    for name in SOURCES:
        spec = ssd.shapes.SOURCES[name]
        if not spec.redistributable:
            raise SystemExit(f"{name} is licensed {spec.license!r} and must not be "
                             f"baked into bundled data")

    print(f"Building the node table for {len(locations)} locations, levels {list(LEVELS)}")
    coverage = unocha_coverage()
    print(f"  UNOCHA mirror covers {len(coverage)} countries")

    cgaz = {}
    for level in LEVELS:
        cgaz[level] = read_cgaz(level)
        print(f"  geoBoundaries CGAZ ADM{level}: {len(cgaz[level])} features")

    populations, population_year = national_populations()
    print(f"  national populations from bundled WPP, year {population_year}")

    rows, missing = [], []
    for n, row in enumerate(locations.itertuples(), start=1):
        frames = gather(row.location, row.iso3, coverage, cgaz)
        if not frames:
            missing.append(row.location)
            continue
        rows += build_location(row.location, row.iso3, frames, populations)
        if n % 25 == 0 or n == len(locations):
            print(f"    {n}/{len(locations)} locations, {len(rows)} nodes")

    if missing:
        print(f"  WARNING: no boundaries found for {len(missing)}: {sorted(missing)}")

    OUT.mkdir(parents=True, exist_ok=True)
    write(rows, OUT / "nodes.h5", population_year)

    if check:
        ssd.registry.refresh()
        # Check a country that was actually built -- `--limit` may have excluded Kenya.
        built = [r["location"] for r in rows if r["level"] == 1]
        where = "Kenya" if "Kenya" in built else built[0]
        for level in LEVELS:
            nodes = ssd.load_nodes(where, level=level)
            print(f"  check level {level}: load_nodes({where!r}) -> {nodes.shape}, "
                  f"cols={list(nodes.columns)}")
            assert len(nodes) > 0
        d = ssd.distances(where, level=1)
        print(f"  check distances: {d.shape}, max {np.nanmax(d.to_numpy()):.0f} km")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="after building, load the result back and validate it")
    parser.add_argument("--limit", type=int, default=None,
                        help="only build the first N locations (for development)")
    args = parser.parse_args()
    warnings.filterwarnings("ignore", category=RuntimeWarning)   # equal-area centroid noise
    build(limit=args.limit, check=args.check)


if __name__ == "__main__":
    main()
