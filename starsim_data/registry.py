"""
The dataset registry: what datasets exist, where they live, and how to shape them.

Two tables live here.

`DATASETS` maps a dataset name to a `Dataset` descriptor -- its layout, tier, admin
level, license, available UN WPP revisions and location count. Bundled datasets are
discovered once by reading the HDF5 stores in `data/`; anything else can be added with
`register_dataset()`.

`LAYOUTS` maps a layout name to the function that turns a stored array into a dataframe
(`matrix`, `crude`, `mortality`, `population`). This replaces dispatching on
`spec['layout']` through an if-chain, and means a new data family is a new shaper plus a
registry entry rather than another branch inside `load()`.

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
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
from typing import Callable, Optional, Tuple

import h5py
import sciris as sc

__all__ = ["Dataset", "Source", "datasets", "dataset", "register_dataset",
           "unregister_dataset", "register_layout", "get_layout", "data_dir", "refresh"]

# Demographic stores are named `demographics-<revision>.h5`, e.g. demographics-2024.h5.
DEMOGRAPHICS_PREFIX = "demographics-"

# One-line descriptions of the bundled datasets. Everything else about a dataset is read
# from the store itself; these are the only facts that are not in the data.
DESCRIPTIONS = {
    "births": "Crude birth rate (per 1,000), UN WPP",
    "deaths": "Age/sex mortality rate m(x), 5-year abridged, UN WPP",
    "migration": "Crude net-migration rate (per 1,000), UN WPP",
    "population": "Population by 5-year age group and sex (persons), UN WPP",
}
MATRIX_DESCRIPTION = "Age-structured contact matrix by setting"


@dataclass(frozen=True)
class Source:
    """Where one revision of a dataset physically lives."""
    store: str              # bundled file name, e.g. 'demographics-2024.h5'
    group: str = ""         # group within the store; '' means the file root
    revision: str = ""      # UN WPP revision; '' for datasets not versioned this way


@dataclass(frozen=True)
class Dataset:
    """What a dataset is: its shape, its provenance and where to get it.

    Attributes:
        name (str): the dataset name, as passed to `load(which=...)`.
        layout (str): how the values are stored; see `LAYOUTS`.
        tier (int): 0 bundled in the wheel, 1 downloaded release asset, 2 fetched upstream.
        level (int): administrative level (0 = country).
        sources (tuple): `Source` records, oldest revision first.
        license (str): the upstream data license, e.g. `'CC BY 3.0 IGO'`.
        n_locations (int): how many locations the dataset covers.
        description (str): a one-line summary.
        loader (callable): if set, `load()` delegates to it instead of reading a bundled
            store -- the hook for registering a dataset this package does not ship.
    """
    name: str
    layout: str
    tier: int = 0
    level: int = 0
    sources: Tuple[Source, ...] = ()
    license: str = ""
    n_locations: int = 0
    description: str = ""
    loader: Optional[Callable] = field(default=None, repr=False)

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
            raise ValueError(f"dataset {self.name!r} has no bundled store (tier {self.tier})")
        if revision is None:
            return self.sources[-1]
        if not self.revisions:
            raise ValueError(f"revision={revision!r} does not apply to {self.name!r}; contact "
                             f"sources are already versioned by name (see list_datasets())")
        for source in self.sources:
            if source.revision == str(revision):
                return source
        raise ValueError(f"unknown revision {revision!r}; available: {list(self.revisions)}")


# --- Layouts ---------------------------------------------------------------------- #

LAYOUTS = {}


def register_layout(name, shaper, overwrite=False):
    """Register a function that turns a stored array into a dataframe.

    Args:
        name (str): the layout name, matching `spec['layout']` in the store.
        shaper (callable): called as `shaper(group, key, spec, kind)` and returning a
            `sciris.dataframe`.
        overwrite (bool): whether to replace an existing layout of the same name.
    """
    if name in LAYOUTS and not overwrite:
        raise ValueError(f"layout {name!r} is already registered; pass overwrite=True to replace it")
    LAYOUTS[name] = shaper
    return shaper


def get_layout(name):
    """Return the shaper registered for a layout.

    Raises:
        ValueError: if the layout is unknown.
    """
    if name not in LAYOUTS:
        raise ValueError(f"unrecognized layout {name!r}; registered layouts are "
                         f"{sorted(LAYOUTS)}")
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
    return resources.files("starsim_data") / "data"


def _spec(node):
    raw = node.attrs.get("spec")
    return json.loads(raw) if raw is not None else {"layout": "matrix"}


def _license(f):
    raw = f.attrs.get("provenance")
    return json.loads(raw).get("license", "") if raw is not None else ""


@lru_cache(maxsize=1)
def _discover():
    """Build descriptors for the bundled stores by reading them once."""
    found = {}
    for path in sorted(data_dir().iterdir()):
        if not path.name.endswith(".h5"):
            continue
        revision = ""
        if path.name.startswith(DEMOGRAPHICS_PREFIX):
            revision = path.name[len(DEMOGRAPHICS_PREFIX):-len(".h5")]
        with h5py.File(path, "r") as f:
            license_ = _license(f)
            # A demographic store holds one group per series; a contact store is itself
            # a single dataset whose groups are locations.
            groups = {name: f[name] for name in f} if revision else {"": f}
            for group_name, node in groups.items():
                name = group_name or path.name[:-len(".h5")]
                source = Source(store=path.name, group=group_name, revision=revision)
                existing = found.get(name)
                if existing is not None:  # another revision of the same series
                    found[name] = replace(existing,
                                          sources=tuple(sorted(existing.sources + (source,),
                                                               key=lambda s: s.revision)),
                                          n_locations=max(existing.n_locations, len(node)))
                    continue
                spec = _spec(node)
                found[name] = Dataset(name=name,
                                      layout=spec["layout"],
                                      tier=0,
                                      level=spec.get("level", 0),
                                      sources=(source,),
                                      license=license_,
                                      n_locations=len(node),
                                      description=DESCRIPTIONS.get(name, MATRIX_DESCRIPTION))
    return found


def refresh():
    """Forget the discovered datasets, so the stores are re-read on next use.

    Only needed if the bundled data changes within a running process, e.g. after a
    rebuild in a test.
    """
    _discover.cache_clear()


def datasets(tier=None):
    """Return every known dataset as `{name: Dataset}`.

    Args:
        tier (int): if given, only datasets in this tier (0 bundled, 1 release asset,
            2 fetched upstream).

    Returns:
        sciris.objdict: name -> `Dataset`, sorted by name.
    """
    merged = dict(_discover())
    merged.update(_REGISTERED)
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
    suggestion = sc.suggest(str(name), list(known), n=3, die=False)
    hint = f" (did you mean: {sc.strjoin(sc.tolist(suggestion))}?)" if suggestion else ""
    raise ValueError(f"unknown dataset {name!r}{hint}; available: {list(known)}")


def register_dataset(dataset, overwrite=False):  # pylint: disable=redefined-outer-name
    """Add a dataset to the registry.

    The hook for data this package does not ship: give the descriptor a `loader`, and
    `load(which=<name>)` will call it as `loader(location, **kwargs)`.

    Args:
        dataset (Dataset): the descriptor to register.
        overwrite (bool): whether to replace an existing dataset of the same name.

    Example:
        >>> import starsim_data as ssd
        >>> ds = ssd.registry.Dataset(name='mydata', layout='crude', tier=2,
        ...                           loader=lambda location, **kw: location)
        >>> ssd.registry.register_dataset(ds)
        >>> ssd.load('Kenya', which='mydata')
        'Kenya'
        >>> ssd.registry.unregister_dataset('mydata')
    """
    if not isinstance(dataset, Dataset):
        raise TypeError(f"expected a Dataset descriptor, got {type(dataset).__name__}")
    if dataset.name in datasets() and not overwrite:
        raise ValueError(f"dataset {dataset.name!r} is already registered; "
                         f"pass overwrite=True to replace it")
    _REGISTERED[dataset.name] = dataset
    return dataset


def unregister_dataset(name):
    """Remove a previously registered dataset. Bundled datasets cannot be removed."""
    if name not in _REGISTERED:
        raise KeyError(f"dataset {name!r} was not registered; registered: {sorted(_REGISTERED)}")
    return _REGISTERED.pop(name)
