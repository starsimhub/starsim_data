"""Shared test configuration."""

import os

import matplotlib
import pytest

import starsim_data as ssd

matplotlib.use("Agg")  # no display in CI, and no windows popping up locally


@pytest.fixture(scope="session", autouse=True)
def isolate_cache(tmp_path_factory):
    """Keep the tests out of the user's real download cache.

    Set `STARSIM_DATA_CACHE_DIR` to reuse downloads between runs of the network tests
    (they fetch a few hundred MB); otherwise each session gets a throwaway directory.
    """
    if not os.environ.get("STARSIM_DATA_CACHE_DIR"):
        ssd.options.cache_dir = str(tmp_path_factory.mktemp("cache"))
    yield
    ssd.options.reset()
