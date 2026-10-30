"""
Load bundled data.

The data ships inside the package under `starsim_data/data/`, keyed by location. There
are two families of dataset, and `load` returns the natural shape for each:

- Contact matrices -- one file per source, each a `layout='matrix'` store. `load`
  returns a square `(n, n)` frame whose rows and columns are indexed by the start age of
  each bin (e.g. `0, 5, ..., 75`); the `kind` argument selects the contact setting
  (`all`, `home`, ...). `prem2021.h5` is bundled; the other sources (`prem2017`,
  `mistry2021`) are the same kind of store, fetched on demand by `fetch()`. The default,
  `prem`, is `prem2021`, or `prem2017` for the ten locations `prem2021` lacks (which
  are bundled, in `prem/prem2017.h5`).
- Demographic time series from UN WPP -- grouped in `demographics-<revision>.h5`, one
  group per series (`births`, `deaths`, `migration`, `population`, `fertility`). `load` returns a
  tidy frame with WPP-native column names, so e.g. `deaths` drops straight into
  `ss.Deaths(death_rate=...)`.

Demographic stores are versioned by UN WPP revision. `load` uses the newest bundled
revision unless `revision=` says otherwise, so a new WPP release is an additive
rebuild rather than a silent change to data already in use; see `list_revisions()`.

`load` never touches the network -- everything it reads is inside the wheel. For the
contact sources that are published but not bundled see `fetch()`, and for data from its
original publisher (annual series, life tables, other projection variants) see
`download()`; both cache what they download.

Locations are resolved by name, ISO-2/ISO-3 code, official name or alias -- see
`starsim_data.locations`. Every `load` result is a `sciris.dataframe`, a drop-in
replacement for a pandas `DataFrame`, carrying its source provenance in `.attrs`.
"""

import h5py
import numpy as np
import sciris as sc
import starsim_data as ssd

__all__ = ['load', 'list_datasets', 'list_locations', 'list_revisions', 'provenance']

# Contact settings available within each contact-matrix dataset.
KINDS = ('all', 'home', 'work', 'school', 'community')


def _data_file(name):
    """Return a filesystem path to a bundled data file, e.g. `prem2021.h5`."""
    return ssd.registry.data_dir() / name


def list_revisions():
    """Return the bundled UN WPP revisions, oldest first; the last is the default.

    Example:
        ```python
        import starsim_data as ssd
        ssd.list_revisions() # Returns ['2024']
        ```
    """
    revisions = set()
    for ds in ssd.registry.datasets().values():
        revisions.update(ds.revisions)
    return sorted(revisions)


def list_datasets(detailed=False, tier=None):
    """Return the available datasets: contact sources plus WPP demographic series.

    Args:
        detailed (bool): if True, return a dataframe of the registry -- name, layout,
            access (bundled, fetched or downloaded), admin level, location count, license
            and revisions -- rather than just the names.
        tier (int): restrict to one tier (0 bundled, 1 fetched, 2 downloaded).

    Returns:
        list or sciris.dataframe: dataset names, or the ssd.registry.

    Example:
        ```python
        import starsim_data as ssd
        'prem2021' in ssd.list_datasets() # Returns True
        ```
    """
    known = ssd.registry.datasets(tier=tier)
    if not detailed:
        return list(known)
    rows = []
    for ds in known.values():
        rows.append(dict(
            dataset     = ds.name,
            description = ds.description,
            layout      = ds.layout,
            access      = ds.access,
            levels      = sc.strjoin(ds.levels),
            locations   = ds.n_locations,
            revisions   = sc.strjoin(ds.revisions),
            license     = ds.license,
        ))
    return sc.dataframe(rows)


def _open(which, revision=None, path=None):
    """Open the store holding `which`, returning (file, group). Caller closes the file.

    For a contact source the group is the file root; for a demographic series it is the
    corresponding group inside the demographic store for `revision`. `path` is where a
    fetched store was downloaded to; a bundled store is found in the package.
    """
    source = ssd.registry.dataset(which).source(revision)
    f = h5py.File(sc.ifelse(path, _data_file(source.store)), 'r')
    group = f[source.group] if source.group else f
    return f, group


def list_locations(which, revision=None):
    """Return the sorted locations available in dataset `which`.

    A fetched dataset lists its locations from the manifest, without downloading it.

    Example:
        ```python
        import starsim_data as ssd
        'Kenya' in ssd.list_locations('prem2021') # Returns True
        ```
    """
    ds = ssd.registry.dataset(which)
    if ds.locations:
        return sorted(ds.locations)
    f, group = _open(which, revision)
    with f:
        locations = sorted(group.keys())
    return locations


def provenance(which=None, revision=None):
    """Return where a dataset came from: source, license, citation and build details.

    Args:
        which (str): dataset name; if None, return a dict keyed by every dataset.
        revision (str/int): for demographic series, the UN WPP revision (default newest).

    Returns:
        sciris.objdict: with keys including `source`, `source_url`, `license`,
        `citation`, `built` and `builder`. Contents vary by source.

    Example:
        ```python
        import starsim_data as ssd
        ssd.provenance('prem2021').license # Returns 'GPL-3.0'
        ```
    """
    if which is None:
        return sc.objdict({name: provenance(name) for name in list_datasets(tier=0)})
    ds = ssd.registry.dataset(which)
    if ds.provenance:  # a fetched store's, as recorded in the manifest
        return sc.objdict(ds.provenance)
    # Provenance is per-store (all series in a demographic store share a source), so
    # read it from the file root rather than the group.
    f, _ = _open(which, revision)
    with f:
        prov = ssd.registry._attr(f, 'provenance', default=None)
    if prov is None:
        return sc.objdict(dataset=which, note='no provenance recorded in this store')
    return sc.objdict(prov)


def _shape_matrix(group, key, spec, opts):
    """Square contact matrix, rows and columns labeled by the start age of each bin."""
    kind = opts['kind']
    if kind not in KINDS:
        raise ValueError(f'kind must be one of {KINDS}, not {kind!r}')
    if kind not in group[key]:
        raise KeyError(f'kind {kind!r} not available for {key!r}')
    mat = np.asarray(group[f'{key}/{kind}'][:], dtype=np.float32)
    ages = spec.get('ages')
    return sc.dataframe(mat, index=ages, columns=ages)


def _shape_crude(group, key, spec, opts):
    """One national value per year, e.g. the crude birth rate."""
    years  = np.asarray(spec['years'])
    values = np.asarray(group[key][:], dtype=np.float32)
    return sc.dataframe({'Time': years, spec['value_col']: values})


def _shape_year_sex_age(group, key, spec, opts):
    """A (year, sex, age) array, melted into a tidy dataframe with WPP-native columns."""
    arr = np.asarray(group[key][:], dtype=np.float32)
    ny, ns, na = arr.shape
    df = sc.dataframe({
        'Time':            np.repeat(spec['years'], ns * na),
        'Sex':             np.tile(np.repeat(spec['sexes'], na), ny),
        spec['age_col']:   np.tile(spec['ages'], ny * ns),
        spec['value_col']: arr.reshape(-1),
    })
    return df


def _shape_year_age(group, key, spec, opts):
    """A (year, age) array, melted into a tidy dataframe, e.g. age-specific fertility."""
    arr = np.asarray(group[key][:], dtype=np.float32)
    ny, na = arr.shape
    df = sc.dataframe({
        'Time':            np.repeat(spec['years'], na),
        spec['age_col']:   np.tile(spec['ages'], ny),
        spec['value_col']: arr.reshape(-1),
    })
    return df


def _shape_nodes(group, key, spec, opts):
    """The node table for one location: one row per administrative unit."""
    arr = group[key][:]
    df = sc.dataframe({name: arr[name] for name in arr.dtype.names})
    for col in df.columns:
        if df[col].dtype == object: # h5py hands back bytes for vlen strings
            df[col] = df[col].str.decode('utf-8')
    level = opts.get('level')
    if level is not None:
        level = ssd.parse_level(level)
        df = df[df.level == level]
        if not len(df):
            raise ValueError(f"no level-{level} nodes for {key!r}; available levels: {spec.get('levels', [])}")
    return df.reset_index(drop=True)


ssd.registry.register_layout('matrix',     _shape_matrix)
ssd.registry.register_layout('crude',      _shape_crude)
ssd.registry.register_layout('mortality',  _shape_year_sex_age)
ssd.registry.register_layout('population', _shape_year_sex_age)
ssd.registry.register_layout('fertility',  _shape_year_age)
ssd.registry.register_layout('nodes',      _shape_nodes)


def load(location, which='prem', kind='all', revision=None, level=None):
    """
    Load data for a location.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias, e.g.
            `'Kenya'`, `'KE'`, `'KEN'`; case-, accent- and punctuation-insensitive.
        which (str): dataset -- the contact matrices (`'prem'`, the default, which
            is `'prem2021'` or, for the ten locations it lacks, `'prem2017'`; or
            `'prem2021'` itself), or a demographic series (`'births'`, `'deaths'`,
            `'migration'`, `'population'`, `'fertility'`). See `list_datasets()`; all of `'prem2017'`
            and `'mistry2021'` are fetched with `fetch()`, and annual series are
            downloaded with `download()`.
        kind (str): for contact-matrix datasets only, the contact setting -- one of
            `'all'`, `'home'`, `'work'`, `'school'`, `'community'`. Ignored otherwise.
        revision (str/int): for demographic series only, the UN WPP revision to read
            (default: the newest bundled). See `list_revisions()`.
        level (int/str): for the node table only, the administrative level to return
            (None returns every level). See `load_nodes()`, the readable spelling of
            `load(..., which='nodes', level=...)`.

    Returns:
        sciris.dataframe: a drop-in replacement for a pandas `DataFrame`, with source
        provenance in `.attrs['provenance']`. For contact matrices, a square `(n, n)`
        matrix whose rows and columns are indexed by the start age of each bin (e.g.
        `0, 5, ..., 75`). For demographic series, a tidy frame -- `births`/`migration`
        have columns `[Time, CBR]`/`[Time, CNMR]`; `deaths` has
        `[Time, Sex, AgeGrpStart, mx]`; `population` has `[Time, Sex, AgeGrp, Value]`;
        `fertility` has `[Time, AgeGrpStart, ASFR]`.

    Raises:
        ValueError: if `which`, `kind` or `revision` is not recognized.
        KeyError: if the location is unknown, or is absent from this dataset.

    Example:
        ```python
        import starsim_data as ssd
        M = ssd.load(location='kenya') # (16, 16) contact matrix
        d = ssd.load(location='KEN', which='deaths') # tidy mortality
        ```
    """
    ds = ssd.registry.dataset(which)
    if ds.loader is not None:  # a registered dataset that is not a bundled store
        return ds.loader(location, kind=kind, revision=revision, level=level)
    if (level is not None) and (ds.layout != 'nodes'):
        raise ValueError(f'level={level!r} does not apply to {which!r}; only the node table is addressed by administrative level')
    if ds.tier > 0: # `load` never touches the network; say so rather than quietly downloading
        raise ValueError(f'{which!r} is not bundled; use {ds.function}({location!r}, which={which!r}) to download it')
    return _read(which, location, kind=kind, revision=revision, level=level)


def _load_prem(location, kind='all', revision=None, level=None):
    """The default contact matrices: `prem2021`, or `prem2017` for a location it lacks."""
    for name, value in dict(revision=revision, level=level).items():
        if value is not None:
            raise ValueError(f'{name}={value!r} does not apply to contact matrices')
    key = ssd.resolve(location)
    if key in list_locations('prem2021'):
        return _read('prem2021', key, kind=kind)
    if key in list_locations('prem'):
        return _read('prem2017', key, kind=kind, path=_data_file(ssd.registry.PREM['fill']))
    return _read('prem2021', location, kind=kind) # Raises, naming the sources that do have it


def _read(which, location, kind='all', revision=None, level=None, path=None):
    """Read one location from the store holding `which` (at `path`, if it was fetched)."""
    f, group = _open(which, revision, path)
    with f:
        spec  = ssd.registry._spec(group)
        key   = ssd.resolve(location, valid=group.keys(), dataset=which)
        opts  = dict(kind=kind, level=level)
        shape = ssd.registry.get_layout(spec['layout'])
        df    = shape(group, key, spec, opts)
        prov  = ssd.registry._attr(f, 'provenance', default=None)
    if prov is not None:
        df.attrs['provenance'] = sc.objdict(prov)
    df.attrs['location'] = key
    df.attrs['dataset']  = which
    return df
