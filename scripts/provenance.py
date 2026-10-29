"""
Build-time provenance stamping, shared by the build scripts.

Dev/CI tool -- NOT part of the installed package. `stamp()` takes the per-source
attribution facts (who published the data, under what license, how to cite it) and
adds the build facts (when, by which script, from which commit), producing the JSON
blob written to each HDF5 store's root `provenance` attribute.

Recording this inside the store rather than in a sidecar file is deliberate: the
provenance cannot then be separated from the data it describes, and
`starsim_data.provenance(which)` can return it for any dataset the user has loaded.
"""

from datetime import datetime, timezone
import sciris as sc

REPO = sc.thispath(__file__).parent


def _version():
    """ Read the package version without importing the package """
    path = REPO / 'starsim_data' / 'version.py'
    for line in path.read_text().splitlines():
        if line.startswith('__version__'):
            return line.split('=', 1)[1].strip().strip("\"'")
    return 'unknown'


def stamp(dataset, builder, **facts):
    """Return a provenance dict for one dataset.

    Args:
        dataset (str): the dataset name, e.g. `'prem2017'`.
        builder (str): the script producing it, e.g. `'scripts/build_hdf5.py'`.
        **facts: per-source attribution -- `source`, `source_url`, `license`,
            `citation`, and anything else worth recording.

    Returns:
        dict: `facts` plus `dataset`, `built`, `builder`, `package_version` and `git`.
    """
    git = sc.gitinfo(str(REPO), die=False)
    return dict(
        dataset         = dataset,
        **facts,
        built           = datetime.now(timezone.utc).isoformat(timespec='seconds'),
        builder         = builder,
        package_version = _version(),
        git             = git,
    )
