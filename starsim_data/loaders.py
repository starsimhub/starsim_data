"""
Load bundled data.

The data ships inside the package under `starsim_data/data/`, keyed by location. There
are two families of dataset, and `load` returns the natural shape for each:

- Contact matrices -- one file per source (`prem2017.h5`, `prem2021.h5`,
  `mistry2021.h5`), each a `layout='matrix'` store. `load` returns a square `(n, n)`
  frame whose rows and columns are indexed by the start age of each bin (e.g.
  `0, 5, ..., 75`); the `kind` argument selects the contact setting (`all`, `home`, ...).
- Demographic time series from UN WPP -- grouped in `demographics-<revision>.h5`, one
  group per series (`births`, `deaths`, `migration`, `population`). `load` returns a
  tidy frame with WPP-native column names, so e.g. `deaths` drops straight into
  `ss.Deaths(death_rate=...)`.

Demographic stores are versioned by UN WPP revision. `load` uses the newest bundled
revision unless `revision=` says otherwise, so a new WPP release is an additive
rebuild rather than a silent change to data already in use; see `list_revisions()`.

`load` never touches the network -- everything it reads is inside the wheel. For data
that is not bundled (annual series, life tables, other projection variants) see
`fetch()`, which downloads and caches.

Locations are resolved by name, ISO-2/ISO-3 code, official name or alias -- see
`starsim_data.locations`. Every `load` result is a `sciris.dataframe`, a drop-in
replacement for a pandas `DataFrame`, carrying its source provenance in `.attrs`.
"""

import json

import h5py
import numpy as np
import sciris as sc
import starsim_data as ssd

__all__ = ["load", "list_datasets", "list_locations", "list_revisions", "provenance"]

# Contact settings available within each contact-matrix dataset.
KINDS = ("all", "home", "work", "school", "community")


def _data_file(name):
    """Return a filesystem path to a bundled data file, e.g. `prem2017.h5`."""
    return ssd.registry.data_dir() / name


def list_revisions():
    """Return the bundled UN WPP revisions, oldest first; the last is the default.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.list_revisions()
        ['2024']
    """
    revisions = set()
    for ds in ssd.registry.datasets().values():
        revisions |= set(ds.revisions)
    return sorted(revisions)


def list_datasets(detailed=False, tier=None):
    """Return the available datasets: contact sources plus WPP demographic series.

    Args:
        detailed (bool): if True, return a dataframe of the registry -- name, layout,
            tier, admin level, location count, license and revisions -- rather than
            just the names.
        tier (int): restrict to one tier (0 bundled, 1 release asset, 2 fetched).

    Returns:
        list or sciris.dataframe: dataset names, or the ssd.registry.

    Example:
        >>> import starsim_data as ssd
        >>> 'prem2017' in ssd.list_datasets()
        True
    """
    known = ssd.registry.datasets(tier=tier)
    if not detailed:
        return list(known)
    return sc.dataframe([dict(dataset=ds.name,
                              description=ds.description,
                              layout=ds.layout,
                              tier=ds.tier,
                              levels=", ".join(str(x) for x in ds.levels),
                              locations=ds.n_locations,
                              revisions=", ".join(ds.revisions),
                              license=ds.license) for ds in known.values()])


def _open(which, revision=None):
    """Open the store holding `which`, returning (file, group). Caller closes the file.

    For a contact source the group is the file root; for a demographic series it is the
    corresponding group inside the demographic store for `revision`.
    """
    source = ssd.registry.dataset(which).source(revision)
    f = h5py.File(_data_file(source.store), "r")
    return f, (f[source.group] if source.group else f)


def list_locations(which, revision=None):
    """Return the sorted locations available in dataset `which`.

    Example:
        >>> import starsim_data as ssd
        >>> 'Kenya' in ssd.list_locations('prem2017')
        True
    """
    f, group = _open(which, revision)
    try:
        return sorted(group.keys())
    finally:
        f.close()


def provenance(which=None, revision=None):
    """Return where a dataset came from: source, license, citation and build details.

    Args:
        which (str): dataset name; if None, return a dict keyed by every dataset.
        revision (str/int): for demographic series, the UN WPP revision (default newest).

    Returns:
        sciris.objdict: with keys including `source`, `source_url`, `license`,
        `citation`, `built` and `builder`. Contents vary by source.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.provenance('prem2017').license
        'GPL-3.0'
    """
    if which is None:
        return sc.objdict({name: provenance(name) for name in list_datasets(tier=0)})
    f, _ = _open(which, revision)
    try:
        # Provenance is per-store (all series in a demographic store share a source),
        # so read it from the file root rather than the group.
        raw = f.attrs.get("provenance")
        if raw is None:
            return sc.objdict(dataset=which, note="no provenance recorded in this store")
        return sc.objdict(json.loads(raw))
    finally:
        f.close()


def _spec(group):
    raw = group.attrs.get("spec")
    return json.loads(raw) if raw is not None else {"layout": "matrix"}


def _melt_year_sex_age(arr, years, sexes, ages, *, age_col, value_col):
    """Melt a (year, sex, age) array into a tidy dataframe with WPP-native columns."""
    ny, ns, na = arr.shape
    return sc.dataframe({
        "Time": np.repeat(years, ns * na),
        "Sex": np.tile(np.repeat(sexes, na), ny),
        age_col: np.tile(ages, ny * ns),
        value_col: np.asarray(arr, dtype=np.float32).reshape(-1),
    })


def _shape_matrix(group, key, spec, opts):
    """Square contact matrix, rows and columns labelled by the start age of each bin."""
    kind = opts["kind"]
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    if kind not in group[key]:
        raise KeyError(f"kind {kind!r} not available for {key!r}")
    mat = np.asarray(group[f"{key}/{kind}"][:], dtype=np.float32)
    ages = spec.get("ages")
    return sc.dataframe(mat, index=ages, columns=ages)


def _shape_crude(group, key, spec, opts):  # pylint: disable=unused-argument
    """One national value per year, e.g. the crude birth rate."""
    return sc.dataframe({"Time": np.asarray(spec["years"]),
                         spec["value_col"]: np.asarray(group[key][:], dtype=np.float32)})


def _shape_year_sex_age(group, key, spec, opts):  # pylint: disable=unused-argument
    """A (year, sex, age) array, melted tidy."""
    return _melt_year_sex_age(group[key][:], np.asarray(spec["years"]),
                              np.asarray(spec["sexes"]), np.asarray(spec["ages"]),
                              age_col=spec["age_col"], value_col=spec["value_col"])


def _shape_nodes(group, key, spec, opts):
    """The node table for one location: one row per administrative unit."""
    arr = group[key][:]
    df = sc.dataframe({name: arr[name] for name in arr.dtype.names})
    for col in df.columns:                      # h5py hands back bytes for vlen strings
        if df[col].dtype == object:
            df[col] = df[col].str.decode("utf-8")
    level = opts.get("level")
    if level is not None:
        level = ssd.parse_level(level)
        df = df[df.level == level]
        if not len(df):
            raise ValueError(f"no level-{level} nodes for {key!r}; available levels: "
                             f"{spec.get('levels', [])}")
    return df.reset_index(drop=True)


ssd.registry.register_layout("matrix", _shape_matrix)
ssd.registry.register_layout("crude", _shape_crude)
ssd.registry.register_layout("mortality", _shape_year_sex_age)
ssd.registry.register_layout("population", _shape_year_sex_age)
ssd.registry.register_layout("nodes", _shape_nodes)


def load(location, which="prem2017", kind="all", revision=None, level=None):
    """
    Load data for a location.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias, e.g.
            `'Kenya'`, `'KE'`, `'KEN'`; case-, accent- and punctuation-insensitive.
        which (str): dataset -- a contact source (`'prem2017'`, `'prem2021'`,
            `'mistry2021'`) or a demographic series (`'births'`, `'deaths'`,
            `'migration'`, `'population'`). See `list_datasets()`.
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
        `[Time, Sex, AgeGrpStart, mx]`; `population` has `[Time, Sex, AgeGrp, Value]`.

    Raises:
        ValueError: if `which`, `kind` or `revision` is not recognized.
        KeyError: if the location is unknown, or is absent from this dataset.

    Example:
        >>> import starsim_data as ssd
        >>> M = ssd.load(location='kenya', which='prem2017')          # (16, 16)
        >>> d = ssd.load(location='KEN', which='deaths')              # tidy mortality
    """
    ds = ssd.registry.dataset(which)
    if ds.loader is not None:  # a registered dataset that is not a bundled store
        return ds.loader(location, kind=kind, revision=revision, level=level)
    if level is not None and ds.layout != "nodes":
        raise ValueError(f"level={level!r} does not apply to {which!r}; only the node "
                         f"table is addressed by administrative level")
    if ds.tier > 0:
        # `load` never touches the network; say so rather than quietly downloading.
        raise ValueError(f"{which!r} is not bundled (tier {ds.tier}); use "
                         f"fetch({location!r}, which={which!r}) to download it")

    f, group = _open(which, revision)
    try:
        spec = _spec(group)
        key = ssd.resolve(location, valid=group.keys(), dataset=which)
        opts = dict(kind=kind, level=level)
        df = ssd.registry.get_layout(spec["layout"])(group, key, spec, opts)

        raw = f.attrs.get("provenance")
        if raw is not None:
            df.attrs["provenance"] = sc.objdict(json.loads(raw))
        df.attrs["location"] = key
        df.attrs["dataset"] = which
        return df
    finally:
        f.close()
