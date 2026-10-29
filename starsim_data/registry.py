"""
The dataset registry: what datasets exist, where they live, and how to shape them.

Two tables live here.

`DATASETS` maps a dataset name to a `Dataset` descriptor -- its layout, tier, admin
level, license, available UN WPP revisions and location count. Bundled datasets are
discovered once by reading the HDF5 stores in `data/`. Stores that are built the same way
but kept out of the wheel (tier 1, fetched on demand by `fetch()`) are described by the
manifest `data/fetched.json`, which `scripts/build_hdf5.py` writes. Anything else can be
added with `register_dataset()`.

`LAYOUTS` maps a layout name to the function that turns a stored array into a dataframe
(`matrix`, `crude`, `mortality`, `population`, `fertility`, `nodes`). This replaces
dispatching on `spec['layout']` through an if-chain, and means a new data family is a new
shaper plus a registry entry rather than another branch inside `load()`.

Both tables have a public registration hook, which is the point: `laser-init`'s registry
is module-level dict literals with no way to extend them, which its own integration
notes identify as a blocker to downstream reuse.

```python
import starsim_data as ssd
ssd.list_datasets(detailed=True)   # the registry as a dataframe
ssd.registry.dataset('deaths')     # one descriptor
```
"""

import json
import dataclasses as dc
import functools as ft
import h5py
import sciris as sc
import starsim_data as ssd

__all__ = ['Dataset', 'Source', 'datasets', 'dataset', 'register_dataset',
           'unregister_dataset', 'register_layout', 'get_layout', 'data_dir', 'refresh']

# Demographic stores are named `demographics-<revision>.h5`, e.g. demographics-2024.h5.
DEMOGRAPHICS_PREFIX = 'demographics-'

# The manifest of stores that are not bundled but fetched (see `scripts/build_hdf5.py`).
FETCHED_MANIFEST = 'fetched.json'

# The default contact matrices, `prem`, are `prem2021`, plus the `prem2017` matrices for
# the locations it lacks, which are bundled in a store of their own in this subfolder.
PREM = dict(name='prem', base='prem2021', fill='prem/prem2017.h5')

# One-line descriptions of the bundled datasets. Everything else about a dataset is read
# from the store itself; these are the only facts that are not in the data.
DESCRIPTIONS = {
    'births': 'Crude birth rate (per 1,000), UN WPP',
    'deaths': 'Age/sex mortality rate m(x), 5-year abridged, UN WPP',
    'migration': 'Crude net-migration rate (per 1,000), UN WPP',
    'population': 'Population by 5-year age group and sex (persons), UN WPP',
    'fertility': 'Age-specific fertility rate (births per 1,000 women), 5-year, UN WPP',
    'nodes': 'Administrative units: centroids, areas, p-codes and hierarchy',
    'adjacency': 'Administrative units that share a border, as pairs of nodeids',
    'prem': 'Contact matrices by setting: prem2021, with prem2017 for the locations it lacks',
}
MATRIX_DESCRIPTION = 'Age-structured contact matrix by setting'


@dc.dataclass(frozen=True)
class Source:
    """Where one revision of a dataset physically lives."""
    store: str              # file name, e.g. 'demographics-2024.h5'
    group: str = ''         # group within the store; '' means the file root
    revision: str = ''      # UN WPP revision; '' for datasets not versioned this way
    url: str = ''           # where a store that is not bundled is downloaded from
    sha256: str = ''        # the digest that download must have

    @property
    def bundled(self):
        """Whether the store ships inside the wheel (rather than being fetched)."""
        return not self.url


@dc.dataclass(frozen=True)
class Dataset:
    """What a dataset is: its shape, its provenance and where to get it.

    Attributes:
        name (str): the dataset name, as passed to `load(which=...)`.
        layout (str): how the values are stored; see `LAYOUTS`.
        tier (int): 0 if the dataset is bundled in the wheel, 1 if it is fetched from
            upstream and cached.
        levels (tuple): the administrative levels covered; `(0,)` for national data.
        sources (tuple): `Source` records, oldest revision first.
        license (str): the upstream data license, e.g. `'CC BY 3.0 IGO'`.
        n_locations (int): how many locations the dataset covers.
        description (str): a one-line summary.
        loader (callable): if set, `load()` delegates to it instead of reading a bundled
            store -- the hook for registering a dataset this package does not ship.
        locations (tuple): for a store that is fetched, the locations it holds, so that
            they can be listed without downloading it.
        provenance (dict): for a store that is fetched, the provenance recorded in it.
    """
    name: str
    layout: str
    tier: int = 0
    levels: tuple = (0,)
    sources: tuple = ()
    license: str = ''
    n_locations: int = 0
    description: str = ''
    loader: object = dc.field(default=None, repr=False)
    locations: tuple = dc.field(default=(), repr=False)
    provenance: dict = dc.field(default_factory=dict, repr=False)

    @property
    def level(self):
        """The finest administrative level available."""
        return max(self.levels)

    @property
    def revisions(self):
        """The available UN WPP revisions, oldest first; empty if not revision-versioned."""
        return tuple(s.revision for s in self.sources if s.revision)

    def source(self, revision=None):
        """Return the `Source` for `revision`, defaulting to the newest available.

        Raises:
            ValueError: if `revision` is given for a dataset that is not versioned by
                revision, or names a revision that is not available.
        """
        if not self.sources:
            raise ValueError(f'dataset {self.name!r} has no bundled store (tier {self.tier})')
        if revision is None:
            return self.sources[-1]
        if not self.revisions:
            errormsg = f'revision={revision!r} does not apply to {self.name!r}; contact sources are already versioned by name (see list_datasets())'
            raise ValueError(errormsg)
        for source in self.sources:
            if source.revision == str(revision):
                return source
        raise ValueError(f'unknown revision {revision!r}; available: {list(self.revisions)}')


# --- Layouts ---------------------------------------------------------------------- #

LAYOUTS = {}


def register_layout(name, shaper, overwrite=False):
    """Register a function that turns a stored array into a dataframe.

    Args:
        name (str): the layout name, matching `spec['layout']` in the store.
        shaper (callable): called as `shaper(group, key, spec, opts)` and returning a
            `sciris.dataframe`. `opts` carries the per-call arguments that apply to some
            layouts but not others -- `kind` for contact matrices, `level` for nodes.
        overwrite (bool): whether to replace an existing layout of the same name.
    """
    if (name in LAYOUTS) and (not overwrite):
        raise ValueError(f'layout {name!r} is already registered; pass overwrite=True to replace it')
    LAYOUTS[name] = shaper
    return shaper


def get_layout(name):
    """Return the shaper registered for a layout.

    Raises:
        ValueError: if the layout is unknown.
    """
    if name not in LAYOUTS:
        raise ValueError(f'unrecognized layout {name!r}; registered layouts are {sorted(LAYOUTS)}')
    return LAYOUTS[name]


# --- Datasets --------------------------------------------------------------------- #

# Datasets registered by the user, merged over the discovered ones by datasets().
_REGISTERED = {}


def data_dir():
    """Return the directory holding the bundled data files.

    The single place the bundled data is located, so that a test (or a rebuild) can
    point the whole package at a different directory by patching this one function --
    followed by `refresh()`, since discovery is cached.
    """
    return sc.thispath(__file__) / 'data'


def _attr(node, key, default):
    """Read a JSON attribute of an HDF5 file or group, e.g. `spec`; `default` if it is absent."""
    raw = node.attrs.get(key)
    if raw is None:
        return default
    return json.loads(raw)


def _spec(node):
    """The layout description of a store or group; a store without one is a contact matrix."""
    return _attr(node, 'spec', default=dict(layout='matrix'))


def _fetched():
    """Build descriptors for the fetched stores, from the manifest."""
    path = data_dir() / FETCHED_MANIFEST
    if not path.is_file():
        return {}
    found = {}
    for name, entry in sc.loadjson(path).items():
        source = Source(store=entry['store'], url=entry['url'], sha256=entry['sha256'])
        found[name] = Dataset(
            name        = name,
            layout      = entry['layout'],
            tier        = 1,
            levels      = tuple(entry.get('levels', [0])),
            sources     = (source,),
            license     = entry['provenance'].get('license', ''),
            n_locations = len(entry['locations']),
            description = entry.get('description', MATRIX_DESCRIPTION),
            locations   = tuple(entry['locations']),
            provenance  = entry['provenance'],
        )
    return found


def _bundled(path, found):
    """Add the descriptors for the dataset(s) in one bundled store to `found`."""
    revision = ''
    if path.name.startswith(DEMOGRAPHICS_PREFIX):
        revision = path.stem[len(DEMOGRAPHICS_PREFIX):]
    with h5py.File(path, 'r') as f:
        lic = _attr(f, 'provenance', default={}).get('license', '')
        groups = {name: f[name] for name in f} if revision else {'': f} # A demographic store holds one group per series; a contact store is itself a single dataset whose groups are locations
        for group, node in groups.items():
            name = group or path.stem
            source = Source(store=path.name, group=group, revision=revision)
            if name in found: # Another revision of the same series
                ds = found[name]
                sources = sorted(ds.sources + (source,), key=lambda s: s.revision)
                found[name] = dc.replace(ds, sources=tuple(sources), n_locations=max(ds.n_locations, len(node)))
            else:
                spec = _spec(node)
                found[name] = Dataset(
                    name        = name,
                    layout      = spec['layout'],
                    tier        = 0,
                    levels      = tuple(spec.get('levels', [spec.get('level', 0)])),
                    sources     = (source,),
                    license     = lic,
                    n_locations = len(node),
                    description = DESCRIPTIONS.get(name, MATRIX_DESCRIPTION),
                )
    return found


@ft.lru_cache(maxsize=1)
def _discover():
    """Build descriptors for the bundled stores by reading them once."""
    found = {}
    for path in sorted(data_dir().glob('*.h5')):
        _bundled(path, found)
    for name, ds in _fetched().items():
        found.setdefault(name, ds) # A bundled store wins over a fetched one
    prem = _prem(found)
    if prem:
        found[prem.name] = prem
    return found


def _prem(found):
    """Describe the default contact matrices, if their stores are present."""
    base = found.get(PREM['base'])
    path = data_dir() / PREM['fill']
    if (base is None) or (not path.is_file()):
        return None
    with h5py.File(data_dir() / base.sources[0].store, 'r') as f:
        locations = set(f.keys())
        prov = json.loads(f.attrs['provenance'])
    with h5py.File(path, 'r') as f:
        locations |= set(f.keys())
        fill = json.loads(f.attrs['provenance'])
    prov.update(dataset=PREM['name'],
                source=f"{prov['source']}, with {fill['source']} for the locations it lacks",
                citation=f"{prov['citation']} {fill['citation']}")
    ds = Dataset(
        name        = PREM['name'],
        layout      = 'matrix',
        tier        = 0,
        license     = base.license,
        n_locations = len(locations),
        description = DESCRIPTIONS[PREM['name']],
        loader      = ssd.loaders._load_prem, # Discovery runs on first use, after loaders is imported
        locations   = tuple(sorted(locations)),
        provenance  = prov,
    )
    return ds


def refresh():
    """Forget the discovered datasets, so the stores are re-read on next use.

    Only needed if the bundled data changes within a running process, e.g. after a
    rebuild in a test.
    """
    _discover.cache_clear()
    return


def datasets(tier=None):
    """Return every known dataset as `{name: Dataset}`.

    Args:
        tier (int): if given, only datasets in this tier (0 bundled, 1 fetched).

    Returns:
        sciris.objdict: name -> `Dataset`, sorted by name.
    """
    merged = sc.mergedicts(_discover(), _REGISTERED)
    if tier is not None:
        merged = {k: v for k, v in merged.items() if v.tier == tier}
    return sc.objdict({name: merged[name] for name in sorted(merged)})


def dataset(name):
    """Return the `Dataset` descriptor for `name`.

    Raises:
        ValueError: if the dataset is unknown; the message lists close matches.
    """
    known = datasets()
    if name in known:
        return known[name]
    hint = ssd.locations._did_you_mean(name, known)
    raise ValueError(f'unknown dataset {name!r}{hint}; available: {list(known)}')


def register_dataset(dataset, overwrite=False):
    """Add a dataset to the registry.

    The hook for data this package does not ship: give the descriptor a `loader`, and
    `load(which=<name>)` will call it as `loader(location, **kwargs)`.

    Args:
        dataset (Dataset): the descriptor to register.
        overwrite (bool): whether to replace an existing dataset of the same name.

    Example:
        >>> import starsim_data as ssd
        >>> ds = ssd.registry.Dataset(name='mydata', layout='crude', tier=1,
        ...                           loader=lambda location, **kw: location)
        >>> ssd.registry.register_dataset(ds)
        >>> ssd.load('Kenya', which='mydata')
        'Kenya'
        >>> ssd.registry.unregister_dataset('mydata')
    """
    if not isinstance(dataset, Dataset):
        raise TypeError(f'expected a Dataset descriptor, got {type(dataset).__name__}')
    if (dataset.name in datasets()) and (not overwrite):
        raise ValueError(f'dataset {dataset.name!r} is already registered; pass overwrite=True to replace it')
    _REGISTERED[dataset.name] = dataset
    return dataset


def unregister_dataset(name):
    """Remove a previously registered dataset. Bundled datasets cannot be removed."""
    if name not in _REGISTERED:
        raise KeyError(f'dataset {name!r} was not registered; registered: {sorted(_REGISTERED)}')
    return _REGISTERED.pop(name)
