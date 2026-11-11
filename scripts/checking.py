"""
Compare a freshly built HDF5 store with the one committed to the repository.

Dev/CI tool -- NOT part of the installed package. Each build script's `--check` builds
into a temporary folder and passes the result here, so that checking never writes to the
repository and does fail if the committed stores have drifted from `raw_data/`.

Values, dtypes, shapes, names and attributes must all match. The only things ignored are
the provenance fields that record *when and from where* a store was built (see
`provenance.stamp`), since those change on every build by design.
"""

import json
import h5py
import numpy as np

# Set by provenance.stamp() and different on every build
VOLATILE = {'built', 'builder', 'package_version', 'git'}


def _attrs(obj):
    """ The attributes of an HDF5 object, with the volatile provenance fields removed """
    out = {}
    for key, value in obj.attrs.items():
        if key == 'provenance':
            value = {k: v for k, v in json.loads(value).items() if k not in VOLATILE}
        elif isinstance(value, np.ndarray):
            value = value.tolist()
        out[key] = value
    return out


def _same(a, b):
    """ Whether two arrays hold the same values; floats to within rounding, so a different BLAS or platform doesn't fail the check """
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.names: # A compound dtype, as in the node table: compare field by field
        return all(_same(a[name], b[name]) for name in a.dtype.names)
    if np.issubdtype(a.dtype, np.floating):
        return np.allclose(a, b, rtol=1e-6, atol=0, equal_nan=True)
    return np.array_equal(a, b)


def compare(built, committed, subset=False):
    """Return a list of the differences between two HDF5 stores, empty if they match.

    Args:
        built (path): the store just built.
        committed (path): the store in the repository.
        subset (bool): if True, the rebuilt store holds only some of the locations (e.g.
            `build_nodes.py --limit`), so compare just those, and skip the root attributes,
            whose counts depend on which were built.
    """
    if not committed.exists():
        return [f'{committed} does not exist']
    diffs = []
    with h5py.File(built, 'r') as new, h5py.File(committed, 'r') as old:
        def visit(name, obj):
            other = old.get(name)
            if other is None:
                diffs.append(f'{name}: only in the rebuilt store')
            elif isinstance(obj, h5py.Dataset) and not _same(obj[()], other[()]):
                diffs.append(f'{name}: values differ')
            elif _attrs(obj) != _attrs(other):
                diffs.append(f'{name}: attributes differ')
        if not subset:
            if _attrs(new) != _attrs(old):
                diffs.append('/: attributes differ')
            old.visititems(lambda name, obj: name in new or diffs.append(f'{name}: only in the committed store'))
        new.visititems(visit)
    return diffs


def report(pairs, subset=False):
    """Compare each (built, committed) pair, print the result, and exit non-zero on any difference.

    Args:
        pairs (list): `(built, committed)` paths.
        subset (bool): passed to `compare()`.
    """
    failed = False
    for built, committed in pairs:
        diffs = compare(built, committed, subset=subset)
        if diffs:
            failed = True
            print(f'  {committed.name}: DIFFERS from a rebuild ({len(diffs)} difference(s)):')
            for diff in diffs[:20]:
                print(f'    {diff}')
            if len(diffs) > 20:
                print(f'    ... and {len(diffs) - 20} more')
        else:
            print(f"  {committed.name}: {'the locations rebuilt match' if subset else 'matches a rebuild'}")
    if failed:
        raise SystemExit('The committed data differs from what the raw data builds; rerun this script without --check and commit the result.')
    return
