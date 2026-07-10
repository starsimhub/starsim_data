"""
Load bundled data.

The data ships inside the package under `starsim_data/data/`, keyed by location. There
are two families of dataset, and `load` returns the natural shape for each:

- Contact matrices -- one file per source (`prem2017.h5`, `prem2021.h5`,
  `mistry2021.h5`), each a `layout='matrix'` store. `load` returns a square `(n, n)`
  DataFrame; the `kind` argument selects the contact setting (`all`, `home`, ...).
- Demographic time series from UN WPP -- grouped in `demographics.h5`, one group per
  series (`births`, `deaths`, `migration`, `population`). `load` returns a tidy
  DataFrame with WPP-native column names, so e.g. `deaths` drops straight into
  `ss.Deaths(death_rate=...)`.
"""

import json
from importlib import resources

import h5py
import numpy as np
import pandas as pd

__all__ = ["load", "list_datasets", "list_locations"]

# Contact settings available within each contact-matrix dataset.
KINDS = ("all", "home", "work", "school", "community")

DEMOGRAPHICS = "demographics.h5"


def _data_dir():
    return resources.files("starsim_data") / "data"


def _data_file(name):
    """Return a filesystem path to a bundled data file, e.g. `prem2017.h5`."""
    return _data_dir() / name


def _match_location(location, keys):
    """Resolve user input like 'kenya' or 'united states' to a stored key like 'Kenya'.

    Matching is case-insensitive and treats spaces and underscores as equivalent.
    Returns the matched key, or None if there is no match.
    """
    def norm(s):
        return s.strip().lower().replace(" ", "_")

    wanted = norm(location)
    for key in keys:
        if norm(key) == wanted:
            return key
    return None


def list_datasets():
    """Return all available datasets: contact sources plus WPP demographic series."""
    names = []
    for p in _data_dir().iterdir():
        if p.name == DEMOGRAPHICS:
            with h5py.File(p, "r") as f:
                names += list(f.keys())          # births, deaths, migration, population
        elif p.name.endswith(".h5"):
            names.append(p.name[:-3])            # prem2017, prem2021, mistry2021
    return sorted(names)


def _open(which):
    """Open the store holding `which`, returning (file, group). Caller closes the file.

    For a contact source the group is the file root; for a demographic series it is the
    corresponding group inside demographics.h5.
    """
    matrix_path = _data_file(f"{which}.h5")
    if matrix_path.is_file():
        f = h5py.File(matrix_path, "r")
        return f, f
    demo_path = _data_file(DEMOGRAPHICS)
    if demo_path.is_file():
        f = h5py.File(demo_path, "r")
        if which in f:
            return f, f[which]
        f.close()
    raise ValueError(f"unknown dataset {which!r}; available: {list_datasets()}")


def list_locations(which):
    """Return the sorted locations available in dataset `which`."""
    f, group = _open(which)
    try:
        return sorted(group.keys())
    finally:
        f.close()


def _spec(group):
    raw = group.attrs.get("spec")
    return json.loads(raw) if raw is not None else {"layout": "matrix"}


def _melt_year_sex_age(arr, years, sexes, ages, age_col, value_col):
    """Melt a (year, sex, age) array into a tidy DataFrame with WPP-native columns."""
    ny, ns, na = arr.shape
    return pd.DataFrame({
        "Time": np.repeat(years, ns * na),
        "Sex": np.tile(np.repeat(sexes, na), ny),
        age_col: np.tile(ages, ny * ns),
        value_col: np.asarray(arr, dtype=np.float32).reshape(-1),
    })


def load(location, which="prem2017", kind="all"):
    """
    Load data for a location.

    Args:
        location (str): location name, e.g. `'Kenya'` (case- and space-insensitive).
        which (str): dataset -- a contact source (`'prem2017'`, `'prem2021'`,
            `'mistry2021'`) or a demographic series (`'births'`, `'deaths'`,
            `'migration'`, `'population'`). See `list_datasets()`.
        kind (str): for contact-matrix datasets only, the contact setting -- one of
            `'all'`, `'home'`, `'work'`, `'school'`, `'community'`. Ignored otherwise.

    Returns:
        pandas.DataFrame: for contact matrices, a square `(n, n)` matrix. For
        demographic series, a tidy frame -- `births`/`migration` have columns
        `[Time, CBR]`/`[Time, CNMR]`; `deaths` has `[Time, Sex, AgeGrpStart, mx]`;
        `population` has `[Time, Sex, AgeGrp, Value]`.

    Example:
        >>> import starsim_data as ssd
        >>> M = ssd.load(location='kenya', which='prem2017')          # (16, 16)
        >>> d = ssd.load(location='kenya', which='deaths')            # tidy mortality
    """
    f, group = _open(which)
    try:
        spec = _spec(group)
        key = _match_location(location, group.keys())
        if key is None:
            raise KeyError(f"location {location!r} not found in {which!r} "
                           f"(have {len(group.keys())} locations; see list_locations({which!r}))")
        layout = spec["layout"]

        if layout == "matrix":
            if kind not in KINDS:
                raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
            if kind not in group[key]:
                raise KeyError(f"kind {kind!r} not available for {location!r} in {which!r}")
            return pd.DataFrame(np.asarray(group[f"{key}/{kind}"][:], dtype=np.float32))

        data = group[key][:]
        if layout == "crude":  # births, migration: one value per year
            return pd.DataFrame({"Time": np.asarray(spec["years"]),
                                 spec["value_col"]: np.asarray(data, dtype=np.float32)})
        if layout in ("mortality", "population"):
            return _melt_year_sex_age(data, np.asarray(spec["years"]), np.asarray(spec["sexes"]),
                                      np.asarray(spec["ages"]), spec["age_col"], spec["value_col"])
        raise ValueError(f"unrecognized layout {layout!r} in {which!r}")  # pragma: no cover
    finally:
        f.close()
