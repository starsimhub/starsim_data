"""
starsim_data: national-level contact matrices for epidemic modeling with Starsim.

This package provides a trimmed, reorganized subset of the contact-matrix data from
epydemix-data (https://github.com/epistorm/epydemix-data): national-level (level 0)
contact matrices only. See NOTICE.md for per-source data licenses and attributions.

The data ships bundled as one HDF5 file per dataset under ``starsim_data/data/``
(e.g. ``prem2017.h5``, ``prem2021.h5``). Load a matrix with :func:`load`::

    import starsim_data as ssd
    df = ssd.load(location='kenya', which='prem2017')
"""

from .load import load, list_datasets, list_locations

__version__ = "0.1.0"

__all__ = ["load", "list_datasets", "list_locations"]
