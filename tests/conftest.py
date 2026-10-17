"""Shared test configuration."""

import os
import shutil
from pathlib import Path

import matplotlib
import pytest

import starsim_data as ssd

# The contact stores that are fetched rather than bundled, as committed in the repository.
FETCHED = Path(__file__).resolve().parent.parent / "fetched"

matplotlib.use("Agg")  # no display in CI, and no windows popping up locally


@pytest.fixture(scope="session", autouse=True)
def isolate_cache(tmp_path_factory):
    """Keep the tests out of the user's real download cache.

    Set `STARSIM_DATA_CACHE_DIR` to reuse downloads between runs of the network tests
    (they fetch a few hundred MB); otherwise each session gets a throwaway directory.
    """
    if not os.environ.get("STARSIM_DATA_CACHE_DIR"):
        ssd.options.cache_dir = str(tmp_path_factory.mktemp("cache"))
    seed_fetched_stores()
    yield
    ssd.options.reset()


def seed_fetched_stores():
    """Put the repository's copies of the fetched stores in the cache, as `fetch()` would.

    So the offline tests can fetch them without the network. The copies are the bytes the
    pinned URLs serve (a test checks their digests against the manifest), so this is what
    a download would give; the `network` tests check the download itself, in a cache of
    their own.
    """
    for name, ds in ssd.registry.datasets(tier=1).items():
        if not ds.sources or ds.source().bundled:
            continue
        source = ds.source()
        path = ssd.cache_dir("stores", create=True) / source.store
        if not path.is_file():
            shutil.copyfile(FETCHED / source.store, path)
            ssd.cache._write_sidecar(path, source.url)
