"""
Fetch data that is too big to bundle.

`load()` is instant, offline and frozen: decadal snapshots of the Medium variant, which
is what almost every model needs, and the default contact matrices (`prem2021`).
`fetch()` covers the things that deliberately did not fit in the wheel:

- **annual** resolution rather than every tenth year,
- **complete life tables** (`qx`, `lx`, `ex`, ...) rather than just `mx`,
- **other projection variants** (High, Low, Constant fertility, ...) rather than Medium,
- **the other contact matrices** (`prem2017`, `mistry2021`), as the same stores `load()`
  reads, downloaded once from this package's own repository at a pinned commit and
  checked against the SHA-256 recorded in `data/fetched.json`.

It works by downloading the UN's bulk CSVs -- the same files `laser-init` uses -- into
the local cache and filtering them per call. No API token is needed (the WPP Data
Portal API requires one; these files do not). The downloads are large, from 17 MB for
the indicator file to 145 MB per half of the abridged life table, so they are cached and
reused; see `cache_info()` and `clear_cache()`.

For the four series that are also bundled, `fetch` returns exactly the schema `load`
returns, so the two are interchangeable apart from resolution. `life_table` and
`indicators` have no bundled counterpart and return the upstream shape.

```python
import starsim_data as ssd
ssd.fetch('kenya', which='deaths', years=(2000, 2025))     # annual mx, not decadal
ssd.fetch('kenya', which='life_table', years=2020)         # qx, lx, ex, ...
ssd.fetch('kenya', which='births', variant='High')         # a different projection
ssd.fetch('kenya', which='indicators', years=(2020, 2030)) # CDR, TFR, LEx, IMR, ...
ssd.fetch('japan', which='prem2017', kind='home')          # a contact source not bundled
```
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import sciris as sc
import starsim_data as ssd

__all__ = ["fetch", "list_fetchable"]

WPP_BASE = ("https://population.un.org/wpp/assets/Excel%20Files/"
            "1_Indicator%20(Standard)/CSV_FILES/")
WPP_URL = "https://population.un.org/wpp/"
WPP_LICENSE = "CC BY 3.0 IGO"
DEFAULT_VARIANT = "Medium"

# Rows are per (location, year, age, sex) for all ~240 WPP locations, so filter while
# reading rather than loading a few hundred MB of other countries into memory.
CHUNK_ROWS = 250_000

# Columns identifying the row rather than carrying data.
META_COLS = ("SortOrder", "LocID", "Notes", "ISO3_code", "ISO2_code", "SDMX_code",
             "LocTypeID", "LocTypeName", "ParentID", "Location", "VarID", "Variant",
             "MidPeriod", "AgeGrpSpan", "SexID")

# Life tables are published in two halves, split at the last estimate year of the
# revision. The boundary moves with each release, so it is recorded per revision rather
# than assumed.
LIFE_TABLE_SPLITS = {"2024": ((1950, 2023), (2024, 2100))}

# The WPP life-table column glossary, ported from `laser-init`'s transformer, which
# documents it inline. This is exactly the sort of note that prevents a units error two
# years later, so it travels with the data: `fetch('...', which='life_table')` attaches
# it to the returned frame as `.attrs['columns']`.
LIFE_TABLE_GLOSSARY = {
    "mx": "central death rate between ages x and x+n",
    "qx": "probability of dying between ages x and x+n",
    "px": "probability of surviving from age x to age x+n",
    "lx": "number of survivors to age x, out of 100,000 births",
    "dx": "number of deaths between ages x and x+n",
    "Lx": "person-years lived between ages x and x+n",
    "Sx": "survival ratio: person-years in age group x+n per person-year in group x",
    "Tx": "person-years lived above age x",
    "ex": "expectation of life at age x",
    "ax": "average years lived between x and x+n by those dying in the interval",
}


@dataclass(frozen=True)
class BulkFile:
    """One of the UN's bulk CSV downloads."""
    stem: str                   # e.g. 'Demographic_Indicators'
    split: bool = False         # published as two halves, by year
    has_variants: bool = True   # whether a non-Medium edition is published
    approx_mb: int = 0          # per file, for the size warning

    def urls(self, revision, variant, years):
        """Return `{filename: url}` for the file(s) covering `years`.

        The UN publishes one file per variant group, so anything other than Medium comes
        out of the (much larger) combined OtherVariants file and is filtered on read.
        """
        tag = DEFAULT_VARIANT if variant == DEFAULT_VARIANT else "OtherVariants"
        if not self.split:
            names = [f"WPP{revision}_{self.stem}_{tag}.csv.gz"]
        else:
            splits = LIFE_TABLE_SPLITS.get(str(revision))
            if splits is None:
                raise ValueError(f"the year split for {self.stem!r} in WPP {revision} is not "
                                 f"known; known revisions: {sorted(LIFE_TABLE_SPLITS)}")
            names = [f"WPP{revision}_{self.stem}_{tag}_{lo}-{hi}.csv.gz"
                     for lo, hi in splits
                     if years is None or any(lo <= y <= hi for y in years)]
        return {name: WPP_BASE + name for name in names}


FILES = {
    "indicators": BulkFile("Demographic_Indicators", approx_mb=17),
    "population": BulkFile("PopulationByAge5GroupSex", approx_mb=30),
    "life_table": BulkFile("Life_Table_Abridged", split=True, has_variants=False, approx_mb=145),
}


@dataclass(frozen=True)
class Series:
    """One fetchable series: which bulk file it comes from and how to shape it."""
    file: str
    shape: str                      # 'crude' | 'long' | 'population' | 'wide'
    value_cols: Tuple[str, ...] = ()
    index_cols: Tuple[str, ...] = ()
    sexes: Tuple[str, ...] = ()     # which Sex values to keep; () keeps all
    description: str = ""


# The four bundled series return exactly what `load()` returns, at annual resolution;
# `life_table` and `indicators` are fetch-only and return the upstream shape.
SERIES = {
    "births": Series("indicators", "crude", value_cols=("CBR",),
                     description="Crude birth rate (per 1,000), annual"),
    "migration": Series("indicators", "crude", value_cols=("CNMR",),
                        description="Crude net-migration rate (per 1,000), annual"),
    "deaths": Series("life_table", "long", value_cols=("mx",), index_cols=("AgeGrpStart",),
                     sexes=("Female", "Male"),
                     description="Age/sex mortality rate m(x), 5-year abridged, annual"),
    "population": Series("population", "population", value_cols=("PopFemale", "PopMale"),
                         index_cols=("AgeGrpStart",),
                         description="Population by 5-year age group and sex (persons), annual"),
    "life_table": Series("life_table", "long", value_cols=tuple(LIFE_TABLE_GLOSSARY),
                         index_cols=("AgeGrpStart",),
                         description="Complete abridged life table (mx, qx, lx, ex, ...), annual"),
    "indicators": Series("indicators", "wide",
                         description="All WPP demographic indicators (CDR, TFR, LEx, IMR, ...)"),
}


def list_fetchable():
    """Return the datasets `fetch()` can retrieve.

    Example:
        >>> import starsim_data as ssd
        >>> 'life_table' in ssd.list_fetchable()
        True
    """
    return sorted(set(SERIES) | set(_fetched_stores()))


def _fetched_stores():
    """The datasets that are stores kept out of the wheel, as {name: Dataset}."""
    return {name: ds for name, ds in ssd.registry.datasets(tier=1).items()
            if ds.sources and not ds.source().bundled}

# [CK: this function and others aren't written in proper starsim style; commands broken up across lines, Path instead of sc.path, too complex, etc.]
def _fetch_store(ds, location, kind, refresh, verbose):
    """Download a store that is not bundled (once), check its digest, and read one location."""
    source = ds.source()
    path = None
    for attempt in ("cached", "fresh"):
        path = ssd.cached_download(source.url, filename=source.store, subdir="stores",
                                   refresh=refresh or attempt == "fresh", verbose=verbose)
        digest = (ssd.cache_provenance(path) or {}).get("sha256")
        if digest == source.sha256:
            break
        if attempt == "fresh":  # a second download that does not match is not used
            for p in (path, Path(str(path) + ssd.cache.SIDECAR_SUFFIX)):
                p.unlink(missing_ok=True)
            raise ValueError(f"the download of {ds.name!r} from {source.url} has SHA-256 "
                             f"{digest}, not the {source.sha256} recorded for it; it was "
                             f"deleted rather than used")
    df = ssd.loaders._read(ds.name, location, kind=kind, path=path)
    df.attrs["provenance"] = sc.objdict(df.attrs.get("provenance", ds.provenance), tier=1,
                                        files=[dict(ssd.cache_provenance(path) or {})])
    return df


def _series(which):
    if which not in SERIES:
        suggestion = sc.suggest(str(which), list_fetchable(), n=3, die=False)
        hint = f" (did you mean: {sc.strjoin(sc.tolist(suggestion))}?)" if suggestion else ""
        raise ValueError(f"cannot fetch {which!r}{hint}; fetchable datasets: {list_fetchable()}")
    return SERIES[which]


def _parse_years(years):
    """Normalize the `years` argument to a sorted list, or None for 'everything'.

    A 2-tuple is an inclusive range; any other collection is an explicit list of years.
    """
    if years is None:
        return None
    if isinstance(years, (int, np.integer)):
        return [int(years)]
    if isinstance(years, tuple) and len(years) == 2:
        start, end = int(years[0]), int(years[1])
        if start > end:
            raise ValueError(f"years={years!r} is an inclusive (start, end) range, but "
                             f"{start} > {end}")
        return list(range(start, end + 1))
    wanted = sorted({int(y) for y in years})
    if not wanted:
        raise ValueError("years is empty")
    return wanted


def _read_filtered(path, iso3, variant, years, usecols):
    """Read one bulk CSV, keeping only the rows for this country, variant and years."""
    frames = []
    reader = pd.read_csv(path, compression="gzip", usecols=usecols, chunksize=CHUNK_ROWS,
                         # Same NA discipline as everywhere else in this package: the only
                         # thing that should become NaN is a genuinely blank cell, not a
                         # country code that happens to spell 'NA'.
                         keep_default_na=False, na_values=[""], low_memory=False)
    for chunk in reader:
        sel = chunk[(chunk["ISO3_code"] == iso3) & (chunk["LocTypeName"] == "Country/Area")]
        if variant is not None:
            sel = sel[sel["Variant"] == variant]
        if years is not None:
            sel = sel[sel["Time"].isin(years)]
        if len(sel):
            frames.append(sel)
    if not frames:
        return pd.DataFrame(columns=list(usecols) if usecols else None)
    return pd.concat(frames, ignore_index=True)


def _needed_columns(series):
    """Return the columns to read for `series`, or None to read them all."""
    if series.shape == "wide":
        return None  # the indicator file is the payload; metadata is dropped afterwards
    cols = ["ISO3_code", "LocTypeName", "Variant", "Time"]
    cols += list(series.index_cols) + list(series.value_cols)
    if series.shape == "long":  # the life table is the only per-sex file
        cols.append("Sex")
    return sorted(set(cols))


def _shape(df, series, which):
    """Turn the filtered upstream rows into this package's schema."""
    if series.shape == "crude":
        out = df[["Time", *series.value_cols]].dropna(subset=list(series.value_cols))
        out = out.sort_values("Time")
    elif series.shape == "population":
        # Upstream is wide (PopFemale/PopMale) and in thousands; `load()` returns tidy
        # rows of absolute persons, so match that.
        out = df.melt(id_vars=["Time", "AgeGrpStart"], value_vars=["PopFemale", "PopMale"],
                      var_name="Sex", value_name="Value")
        out["Sex"] = out["Sex"].str.removeprefix("Pop")
        out["Value"] = out["Value"] * 1000
        out = out.rename(columns={"AgeGrpStart": "AgeGrp"})
        out = out[["Time", "Sex", "AgeGrp", "Value"]].sort_values(["Time", "Sex", "AgeGrp"])
    elif series.shape == "long":
        out = df[df["Sex"].isin(series.sexes)] if series.sexes else df
        out = out[["Time", "Sex", "AgeGrpStart", *series.value_cols]]
        out = out.sort_values(["Time", "Sex", "AgeGrpStart"])
    else:  # 'wide': every indicator column, metadata dropped
        out = df[[c for c in df.columns if c not in META_COLS]].sort_values("Time")

    if out.empty:
        raise ValueError(f"no {which!r} data matched; check the years and variant requested")

    out = out.reset_index(drop=True)  # also detaches from the source frame before casting
    for col in out.columns:
        if col in ("Time", "AgeGrp", "AgeGrpStart"):
            out[col] = out[col].astype(np.int64)
        elif pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].astype(np.float32)
    return sc.dataframe(out)


def fetch(location, which="deaths", years=None, variant=DEFAULT_VARIANT, revision=None,
          refresh=False, verbose=None, kind="all"):
    """
    Fetch data that is not bundled, downloading and caching as needed.

    Unlike `load()`, this touches the network on a cache miss -- deliberately, and under
    a different name, so that `load()`'s "never needs the internet" guarantee stays
    intact and the more expensive call is explicit at the call site.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias, exactly
            as for `load()`.
        which (str): `'births'`, `'deaths'`, `'migration'`, `'population'` (the bundled
            series, at annual resolution), `'life_table'` (the complete abridged life
            table), `'indicators'` (every WPP indicator), or a contact source that is
            not bundled (`'prem2017'`, `'mistry2021'`). See `list_fetchable()`.
        years (int/tuple/list): a single year; a 2-tuple `(start, end)`, treated as an
            inclusive range; or an explicit list of years. None means all of 1950-2100,
            which for life tables means downloading both halves (~290 MB).
        variant (str): the projection variant, e.g. `'Medium'` (default), `'High'`,
            `'Low'`, `'Constant fertility'`. Life tables are Medium-only upstream.
        revision (str/int): the WPP release to fetch, e.g. `2024`. Defaults to the
            newest revision bundled with this package.
        refresh (bool): re-download even if the file is already cached.
        verbose (bool): report progress (default: `options.verbose`).
        kind (str): for a contact source only, the contact setting, as for `load()`.

    Returns:
        sciris.dataframe: for the four bundled series and the contact sources, exactly
        the schema `load()` returns. For `life_table`, `[Time, Sex, AgeGrpStart, mx, qx, px, lx, dx, Lx, Sx,
        Tx, ex, ax]` with a glossary in `.attrs['columns']`. For `indicators`, `Time`
        plus every indicator column. Provenance is in `.attrs['provenance']`.

    Raises:
        ValueError: if `which`, `years`, `variant` or `revision` cannot be satisfied.
        KeyError: if the location is unknown.

    Example:
        >>> import starsim_data as ssd
        >>> d = ssd.fetch('kenya', which='deaths', years=(2020, 2024))  # doctest: +SKIP
        >>> lt = ssd.fetch('KEN', which='life_table', years=2020)       # doctest: +SKIP
        >>> M = ssd.fetch('Japan', which='prem2017', kind='home')       # doctest: +SKIP
    """
    verbose = ssd.options.verbose if verbose is None else verbose # [CK: can use sc.ifelse(verbose, ssd.options.verbose)]
    stores = _fetched_stores()
    if which in stores:
        given = dict(years=years, variant=variant, revision=revision)
        unused = [k for k, v in given.items() if v not in (None, DEFAULT_VARIANT)]
        if unused:  # an argument a dataset has no use for is rejected, not ignored
            raise ValueError(f"{sc.strjoin(unused)} does not apply to {which!r}, a contact "
                             f"source; only kind= does")
        return _fetch_store(stores[which], location, kind, refresh, verbose)
    if kind != "all":
        raise ValueError(f"kind={kind!r} does not apply to {which!r}; only contact sources "
                         f"have contact settings")
    series = _series(which)
    bulk = FILES[series.file]
    wanted_years = _parse_years(years)
    revision = str(revision) if revision is not None else ssd.list_revisions()[-1]

    if not bulk.has_variants and variant != DEFAULT_VARIANT:
        raise ValueError(f"the UN publishes {which!r} for the Medium variant only, not "
                         f"{variant!r}; other variants are available for "
                         f"{sorted(n for n, s in SERIES.items() if FILES[s.file].has_variants)}")

    key = ssd.resolve(location)
    iso3 = ssd.location_info(key).iso3
    if not iso3:
        raise KeyError(f"location {location!r} has no ISO-3 code, so it cannot be matched "
                       f"against the WPP bulk files")

    urls = bulk.urls(revision, variant, wanted_years)
    if verbose:
        print(f"Fetching {which!r} for {key} from UN WPP {revision} ({variant}); "
              f"up to ~{len(urls) * bulk.approx_mb} MB to download on first use")

    usecols = _needed_columns(series)
    frames, paths = [], []
    for filename, url in urls.items():
        path = ssd.cached_download(url, filename=filename, subdir="wpp", refresh=refresh,
                               verbose=verbose)
        paths.append(path)
        frames.append(_read_filtered(path, iso3, variant, wanted_years, usecols))
    raw = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    if raw.empty:
        raise ValueError(f"no rows for {key} ({iso3}) in WPP {revision} {variant!r}; "
                         f"requested years: {years!r}")

    df = _shape(raw, series, which)
    df.attrs["location"] = key
    df.attrs["dataset"] = which
    df.attrs["provenance"] = sc.objdict(
        dataset=which,
        source=f"UN World Population Prospects {revision}",
        source_url=WPP_URL,
        license=WPP_LICENSE,
        citation=(f"United Nations, Department of Economic and Social Affairs, Population "
                  f"Division ({revision}). World Population Prospects {revision}."),
        variant=variant,
        revision=revision,
        tier=1,
        files=[dict(ssd.cache_provenance(path) or {}) for path in paths],
    )
    if which == "life_table":
        df.attrs["columns"] = sc.objdict(LIFE_TABLE_GLOSSARY)
    return df


# Register the two fetch-only datasets so the registry describes everything this package
# knows about, at whatever tier. They have no `loader`, so `load()` refuses them with a
# pointer to `fetch()` rather than silently reaching for the network.
for _name in ("life_table", "indicators"):
    _s = SERIES[_name]
    ssd.registry.register_dataset(ssd.registry.Dataset(
        name=_name,
        layout="long" if _s.shape == "long" else _s.shape,
        tier=1,
        license=WPP_LICENSE,
        description=_s.description,
    ))
