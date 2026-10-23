"""Shared test configuration."""

import os
import shutil
import tempfile

import matplotlib
import pytest
import sciris as sc

import starsim_data as ssd

# The contact stores that are fetched rather than bundled, as committed in the repository.
FETCHED = sc.thispath(__file__).parent / "fetched"

matplotlib.use("Agg")  # no display in CI, and no windows popping up locally


def pytest_configure(config):
    """Tests return their most interesting object, Starsim-style, for use when run as scripts."""
    config.addinivalue_line("filterwarnings", "ignore::pytest.PytestReturnNotNoneWarning")


def isolate_cache(folder=None):
    """Keep the tests out of the user's real download cache.

    Set `STARSIM_DATA_CACHE_DIR` to reuse downloads between runs of the network tests
    (they fetch a few hundred MB); otherwise each session gets a throwaway directory. The
    fixture below calls this under pytest; a test file run as a script calls it from its
    `__main__` block, since pytest does not load this file then.
    """
    if not os.environ.get("STARSIM_DATA_CACHE_DIR"):
        ssd.options.cache_dir = str(folder or tempfile.mkdtemp())
    seed_fetched_stores()


@pytest.fixture(scope="session", autouse=True)
def isolated_cache(tmp_path_factory):
    isolate_cache(tmp_path_factory.mktemp("cache"))
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
