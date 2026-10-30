"""
Fetch the data this package publishes but does not bundle.

Some stores are built exactly like the bundled ones but are too large, or needed by too
few users, to go in the wheel: the full `prem2017` and `mistry2021` contact matrices,
and the US states' (`mistry2021_us`, `population_us`). They are published as files with
this package's releases, listed with their locations and provenance in
`data/fetched.json`. `fetch()` downloads one the first time it is used, checks it
against the SHA-256 recorded there, caches it, and reads it as `load()` does -- so a
given version of the package fixes their contents exactly, as it does for bundled data.

Anything else that is not bundled comes from the organization that publishes it, through
`download()`. `fetch()` passes such a request on to `download()` with a warning, so
that reaching a server this package does not control is never a surprise.

```python
import starsim_data as ssd
ssd.fetch('japan', which='prem2017', kind='home')                      # a contact source not bundled
ssd.fetch('United States:Massachusetts', which='population_us')        # a US state's population
```
"""

import sciris as sc
import starsim_data as ssd

__all__ = ['fetch', 'list_fetchable']


def fetch(location, which, kind='all', refresh=False, verbose=None, **kwargs):
    """
    Fetch a store this package publishes but does not bundle, caching it for next time.

    Unlike `load()`, this touches the network on a cache miss -- deliberately, and under
    a different name, so that `load()`'s "never needs the internet" guarantee stays
    intact. What it downloads is a file published with this package's releases and
    checked against its recorded SHA-256, so it is the same for everyone on a version.

    Data that is not packaged at all, such as annual UN WPP series, is passed on to
    `download()`, with a warning that it comes from an external source.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias, exactly
            as for `load()`. A US state is `'United States:Massachusetts'`; see `resolve()`.
        which (str): a contact source that is not bundled (`'prem2017'`, `'mistry2021'`,
            and `'mistry2021_us'` for the US states), or `'population_us'` (the
            population of each US state by single year of age). See `list_fetchable()`.
        kind (str): for a contact source only, the contact setting, as for `load()`.
        refresh (bool): re-download even if the file is already cached.
        verbose (bool): report progress (default: `options.verbose`).
        kwargs (dict): for data that is not packaged, passed to `download()` (`years`,
            `variant`, `revision`).

    Returns:
        sciris.dataframe: exactly the schema `load()` returns for the same layout;
        `population_us` has that of `population`, for the one year 2023 and `Sex`
        `'Both sexes'`. Provenance is in `.attrs['provenance']`.

    Raises:
        ValueError: if `which` is not fetchable, or an argument does not apply to it.
        KeyError: if the location is unknown, or is absent from this dataset.

    Example:
        ```python
        import starsim_data as ssd
        M = ssd.fetch('Japan', which='prem2017', kind='home')
        ```
    """
    stores = _fetched_stores()
    if which not in stores:
        if which in ssd.list_downloadable(): # Not packaged: say where it is coming from, then get it
            if kind != 'all':
                raise ValueError(f'kind={kind!r} does not apply to {which!r}; only contact sources have contact settings')
            bundled = which in ssd.list_datasets() and ssd.registry.dataset(which).tier == 0
            what = f'{which!r} beyond the bundled decadal series' if bundled else repr(which)
            ssd.downloading._external(what, f'UN WPP ({ssd.downloading.WPP_URL})', f'download({location!r}, which={which!r})')
            return ssd.download(location, which=which, refresh=refresh, verbose=verbose, **kwargs)
        fetchable = list_fetchable()
        hint = ssd.locations._did_you_mean(which, fetchable + ssd.list_downloadable())
        raise ValueError(f'cannot fetch {which!r}{hint}; fetchable datasets: {fetchable}, and see list_downloadable()')

    ds = stores[which]
    unused = list(kwargs)
    if (ds.layout != 'matrix') and (kind != 'all'):
        unused.append('kind')
    if unused: # An argument a dataset has no use for is rejected, not ignored
        takes = 'only kind= does' if ds.layout == 'matrix' else 'it takes only the location'
        raise ValueError(f'{sc.strjoin(unused)} does not apply to {which!r}, a stored {ds.layout!r} dataset; {takes}')
    verbose = sc.ifelse(verbose, ssd.options.verbose)
    return _fetch_store(ds, location, kind, refresh, verbose)


def list_fetchable():
    """Return the datasets `fetch()` can retrieve: the stores published with this package.

    Example:
        ```python
        import starsim_data as ssd
        'mistry2021' in ssd.list_fetchable() # Returns True
        ```
    """
    return sorted(_fetched_stores())


def _fetched_stores():
    """The datasets that are stores kept out of the wheel, as {name: Dataset}."""
    stores = {}
    for name, ds in ssd.registry.datasets(tier=1).items():
        if ds.sources and (not ds.source().bundled):
            stores[name] = ds
    return stores


def _download_store(source, refresh, verbose):
    """Download a store into the cache (if it is not there already), returning its path and SHA-256."""
    path = ssd.cached_download(source.url, filename=source.store, subdir='stores', refresh=refresh, verbose=verbose)
    digest = (ssd.cache_provenance(path) or {}).get('sha256')
    return path, digest


def _fetch_store(ds, location, kind, refresh, verbose):
    """Download a store that is not bundled (once), check its digest, and read one location."""
    source = ds.source()
    ssd.resolve(location, valid=ds.locations, dataset=ds.name) # From the manifest, so a location the store lacks is refused before downloading it

    # Use the cached copy if its digest is right, and download it afresh if not
    path, digest = _download_store(source, refresh, verbose)
    if digest != source.sha256:
        path, digest = _download_store(source, True, verbose)

    # A second download that does not match is not used
    if digest != source.sha256:
        path.unlink(missing_ok=True)
        ssd.cache._sidecar(path).unlink(missing_ok=True)
        errormsg = f'the download of {ds.name!r} from {source.url} has SHA-256 {digest}, not the {source.sha256} recorded for it; it was deleted rather than used'
        raise ValueError(errormsg)

    df = ssd.loaders._read(ds.name, location, kind=kind, path=path)
    prov = df.attrs.get('provenance', ds.provenance)
    df.attrs['provenance'] = sc.objdict(prov, tier=1, files=[dict(ssd.cache_provenance(path) or {})])
    return df
