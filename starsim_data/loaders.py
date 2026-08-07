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

Locations are resolved by name, ISO-2/ISO-3 code, official name or alias -- see
`starsim_data.locations`. Every `load` result is a `sciris.dataframe`, a drop-in
replacement for a pandas `DataFrame`, carrying its source provenance in `.attrs`.
"""

import json
from importlib import resources

import h5py
import numpy as np
import sciris as sc

from .locations import resolve

__all__ = ["load", "list_datasets", "list_locations", "list_revisions", "provenance"]

# Contact settings available within each contact-matrix dataset.
KINDS = ("all", "home", "work", "school", "community")

# Demographic stores are named `demographics-<revision>.h5`, e.g. demographics-2024.h5.
DEMOGRAPHICS_PREFIX = "demographics-"


def _data_dir():
    return resources.files("starsim_data") / "data"


def _data_file(name):
    """Return a filesystem path to a bundled data file, e.g. `prem2017.h5`."""
    return _data_dir() / name


def _demographics_stores():
    """Return `{revision: path}` for the bundled demographic stores."""
    stores = {}
    for path in _data_dir().iterdir():
        if path.name.startswith(DEMOGRAPHICS_PREFIX) and path.name.endswith(".h5"):
            stores[path.name[len(DEMOGRAPHICS_PREFIX):-len(".h5")]] = path
    return stores


def list_revisions():
    """Return the bundled UN WPP revisions, oldest first; the last is the default."""
    return sorted(_demographics_stores())


def list_datasets():
    """Return all available datasets: contact sources plus WPP demographic series."""
    names = []
    for path in _data_dir().iterdir():
        if not path.name.endswith(".h5"):
            continue
        if path.name.startswith(DEMOGRAPHICS_PREFIX):
            with h5py.File(path, "r") as f:
                names += list(f.keys())         # births, deaths, migration, population
        else:
            names.append(path.name[:-len(".h5")])   # prem2017, prem2021, mistry2021
    return sorted(set(names))


def _open(which, revision=None):
    """Open the store holding `which`, returning (file, group). Caller closes the file.

    For a contact source the group is the file root; for a demographic series it is the
    corresponding group inside the demographic store for `revision`.
    """
    matrix_path = _data_file(f"{which}.h5")
    if matrix_path.is_file():
        if revision is not None:
            raise ValueError(f"revision={revision!r} does not apply to {which!r}; contact "
                             f"sources are already versioned by name (see list_datasets())")
        f = h5py.File(matrix_path, "r")
        return f, f

    stores = _demographics_stores()
    if revision is None:
        wanted = sorted(stores)[-1:]            # newest bundled revision
    else:
        wanted = [str(revision)] if str(revision) in stores else []
        if not wanted:
            raise ValueError(f"unknown revision {revision!r}; available: {sorted(stores)}")

    for rev in wanted:
        f = h5py.File(stores[rev], "r")
        if which in f:
            return f, f[which]
        f.close()

    raise ValueError(f"unknown dataset {which!r}; available: {list_datasets()}")


def list_locations(which, revision=None):
    """Return the sorted locations available in dataset `which`."""
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
        return sc.objdict({name: provenance(name) for name in list_datasets()})
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


def load(location, which="prem2017", kind="all", revision=None):
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
    f, group = _open(which, revision)
    try:
        spec = _spec(group)
        key = resolve(location, valid=group.keys(), dataset=which)
        layout = spec["layout"]

        if layout == "matrix":
            if kind not in KINDS:
                raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
            if kind not in group[key]:
                raise KeyError(f"kind {kind!r} not available for {location!r} in {which!r}")
            mat = np.asarray(group[f"{key}/{kind}"][:], dtype=np.float32)
            # Label both axes with the start age of each bin (e.g. 0, 5, ..., 75), so
            # rows/columns index by age rather than by position.
            ages = spec.get("ages")
            df = sc.dataframe(mat, index=ages, columns=ages)
        elif layout == "crude":  # births, migration: one value per year
            data = group[key][:]
            df = sc.dataframe({"Time": np.asarray(spec["years"]),
                               spec["value_col"]: np.asarray(data, dtype=np.float32)})
        elif layout in ("mortality", "population"):
            data = group[key][:]
            df = _melt_year_sex_age(data, np.asarray(spec["years"]), np.asarray(spec["sexes"]),
                                    np.asarray(spec["ages"]),
                                    age_col=spec["age_col"], value_col=spec["value_col"])
        else:
            raise ValueError(f"unrecognized layout {layout!r} in {which!r}")  # pragma: no cover

        raw = f.attrs.get("provenance")
        if raw is not None:
            df.attrs["provenance"] = sc.objdict(json.loads(raw))
        df.attrs["location"] = key
        df.attrs["dataset"] = which
        return df
    finally:
        f.close()
