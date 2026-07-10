"""
Load bundled contact-matrix data.

The data ships inside the package as one HDF5 file per dataset (``prem2017.h5``,
``prem2021.h5``, ...) under ``starsim_data/data/``, each keyed by location with one
matrix per contact layer. This module resolves those files and returns matrices as
pandas DataFrames.
"""

from importlib import resources

import h5py
import numpy as np
import pandas as pd

__all__ = ["load", "list_datasets", "list_locations"]

# Contact layers available within each dataset.
KINDS = ("all", "home", "work", "school", "community")


def _data_file(name):
    """Return a filesystem path to a bundled data file, e.g. ``prem2017.h5``."""
    return resources.files("starsim_data") / "data" / name


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
    """Return the available datasets (contact sources), e.g. ``['prem2017', 'prem2021']``."""
    data_dir = resources.files("starsim_data") / "data"
    return sorted(p.name[:-3] for p in data_dir.iterdir() if p.name.endswith(".h5"))


def list_locations(which):
    """Return the sorted locations available in dataset ``which`` (e.g. 'prem2017')."""
    with h5py.File(_data_file(f"{which}.h5"), "r") as f:
        return sorted(f.keys())


def load(location, which="prem2017", kind="all"):
    """
    Load a contact matrix.

    Args:
        location (str): location name, e.g. ``'Kenya'`` (case- and space-insensitive).
        which (str): dataset / contact source, e.g. ``'prem2017'`` or ``'prem2021'``.
        kind (str): contact layer -- one of ``'all'``, ``'home'``, ``'work'``,
            ``'school'``, ``'community'``.

    Returns:
        pandas.DataFrame: the (n, n) contact matrix as float32.

    Example:
        >>> import starsim_data as ssd
        >>> df = ssd.load(location='kenya', which='prem2017')
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")

    h5_path = _data_file(f"{which}.h5")
    if not h5_path.is_file():
        raise ValueError(f"unknown dataset {which!r}; available: {list_datasets()}")

    with h5py.File(h5_path, "r") as f:
        key = _match_location(location, f.keys())
        if key is None:
            raise KeyError(f"location {location!r} not found in {which!r} "
                           f"(have {len(f.keys())} locations; see list_locations({which!r}))")
        if kind not in f[key]:
            raise KeyError(f"kind {kind!r} not available for {location!r} in {which!r}")
        mat = f[f"{key}/{kind}"][:]

    return pd.DataFrame(np.asarray(mat, dtype=np.float32))
