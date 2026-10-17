"""Tests for the starsim_data loader."""

import hashlib
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import sciris as sc
import pytest

import starsim_data as ssd

# The contact stores that are fetched rather than bundled, as committed in the repository.
FETCHED = Path(__file__).resolve().parent.parent / "fetched"


def test_list_datasets():
    datasets = ssd.list_datasets()
    assert "prem2017" in datasets
    assert "prem2021" in datasets
    # Returned sorted with no duplicates.
    assert datasets == sorted(set(datasets))


def test_list_locations():
    locs = ssd.list_locations("prem2021")
    assert "Kenya" in locs
    assert locs == sorted(locs)


def test_load_returns_sciris_dataframe():
    df = ssd.load(location="Kenya", which="prem2021")
    assert isinstance(df, sc.dataframe)  # drop-in replacement for a pandas DataFrame
    assert isinstance(df, pd.DataFrame)
    assert df.shape == (16, 16)          # prem sources are 16 five-year age bins
    assert df.to_numpy().dtype == np.float32


def test_matrix_axes_are_start_ages():
    df = ssd.load(location="Kenya", which="prem2021")
    # prem's 16 five-year bins -> rows/columns labelled 0, 5, ..., 75.
    assert list(df.index) == list(range(0, 80, 5))
    assert list(df.columns) == list(range(0, 80, 5))

    m = ssd.fetch(location=ssd.list_locations("mistry2021")[0], which="mistry2021")
    assert list(m.index) == list(range(85))          # single-year bins 0..84


def test_mistry_matrix_shape():
    loc = ssd.list_locations("mistry2021")[0]
    df = ssd.fetch(location=loc, which="mistry2021")
    assert df.shape == (85, 85)          # mistry2021 is 85 single-year age bins


@pytest.mark.parametrize("name", ["Kenya", "kenya", "KENYA", " kenya "])
def test_location_matching_is_case_and_space_insensitive(name):
    a = ssd.load(location=name, which="prem2021")
    b = ssd.load(location="Kenya", which="prem2021")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


def test_spaces_map_to_underscores():
    a = ssd.load(location="united states", which="prem2021")
    b = ssd.load(location="United_States", which="prem2021")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


@pytest.mark.parametrize("alias", ["KE", "KEN", "Republic of Kenya"])
def test_load_accepts_iso_codes_and_official_names(alias):
    a = ssd.load(location=alias, which="prem2021")
    b = ssd.load(location="Kenya", which="prem2021")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


def test_load_accepts_abbreviations():
    a = ssd.load(location="USA", which="prem2021")
    b = ssd.load(location="United_States", which="prem2021")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


def test_kinds_differ_and_all_are_loadable():
    mats = {k: ssd.load("Kenya", which="prem2021", kind=k).to_numpy()
            for k in ("all", "home", "work", "school", "community")}
    # The combined matrix should differ from at least one component layer.
    assert any(not np.array_equal(mats["all"], mats[k])
               for k in ("home", "work", "school", "community"))


def test_unknown_dataset_raises_valueerror():
    with pytest.raises(ValueError):
        ssd.load("Kenya", which="does_not_exist")


def test_bad_kind_raises_valueerror():
    with pytest.raises(ValueError):
        ssd.load("Kenya", which="prem2021", kind="bogus")


def test_unknown_location_raises_keyerror():
    with pytest.raises(KeyError):
        ssd.load("Atlantis", which="prem2021")


def test_location_absent_from_dataset_raises_keyerror():
    # Kenya exists in prem2021 but not in mistry2021's smaller country set.
    assert "Kenya" not in ssd.list_locations("mistry2021")
    with pytest.raises(KeyError):
        ssd.fetch("Kenya", which="mistry2021")


def test_default_contact_source_is_prem2021():
    assert ssd.load("Kenya").equals(ssd.load("Kenya", which="prem2021"))


def test_location_missing_from_prem2021_points_at_the_sources_that_have_it():
    with pytest.raises(KeyError, match=r"fetch\('Japan', which='mistry2021'\) or fetch\('Japan', which='prem2017'\)"):
        ssd.load("Japan")
    with pytest.raises(KeyError, match=r"fetch\('Haiti', which='prem2017'\)"):
        ssd.load("Haiti")


@pytest.mark.parametrize("which", ["prem2017", "mistry2021"])
def test_fetched_contact_sources(which):
    """The contact sources that are not bundled are tier 1: listed, and fetched as load() reads."""
    assert ssd.registry.dataset(which).tier == 1
    assert which in ssd.list_fetchable()
    with pytest.raises(ValueError, match="not bundled.*use fetch"):
        ssd.load("France", which=which)
    df = ssd.fetch("France", which=which, kind="home")
    assert df.attrs["dataset"] == which and df.attrs["provenance"].tier == 1
    assert len(ssd.list_locations(which)) == ssd.registry.dataset(which).n_locations


def test_manifest_matches_the_committed_stores():
    """The digest fetch() checks must be that of the store in fetched/, or a download would be refused."""
    for name in ("prem2017", "mistry2021"):
        source = ssd.registry.dataset(name).source()
        assert hashlib.sha256((FETCHED / source.store).read_bytes()).hexdigest() == source.sha256


def test_fetch_rejects_arguments_that_do_not_apply():
    with pytest.raises(ValueError, match="does not apply"):
        ssd.fetch("France", which="prem2017", years=2020)
    with pytest.raises(ValueError, match="does not apply"):
        ssd.fetch("Kenya", which="deaths", kind="home")


@pytest.mark.network
@pytest.mark.parametrize("which", ["prem2017", "mistry2021"])
def test_fetch_downloads_the_pinned_store(which, tmp_path):
    """The pinned URL serves the bytes the manifest records, and fetch() reads them."""
    before = ssd.options.cache_dir
    ssd.options.cache_dir = str(tmp_path) # A cache of its own, without the seeded copies
    try:
        df = ssd.fetch("France", which=which, verbose=False)
        assert df.attrs["provenance"].files[0]["sha256"] == ssd.registry.dataset(which).source().sha256
        with h5py.File(FETCHED / f"{which}.h5", "r") as f:
            assert np.array_equal(df.to_numpy(), f["France/all"][:])
    finally:
        ssd.options.cache_dir = before
