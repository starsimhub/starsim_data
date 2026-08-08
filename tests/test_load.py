"""Tests for the starsim_data loader."""

import numpy as np
import pandas as pd
import sciris as sc
import pytest

import starsim_data as ssd


def test_list_datasets():
    datasets = ssd.list_datasets()
    assert "prem2017" in datasets
    assert "prem2021" in datasets
    # Returned sorted with no duplicates.
    assert datasets == sorted(set(datasets))


def test_list_locations():
    locs = ssd.list_locations("prem2017")
    assert "Kenya" in locs
    assert locs == sorted(locs)


def test_load_returns_sciris_dataframe():
    df = ssd.load(location="Kenya", which="prem2017")
    assert isinstance(df, sc.dataframe)  # drop-in replacement for a pandas DataFrame
    assert isinstance(df, pd.DataFrame)
    assert df.shape == (16, 16)          # prem sources are 16 five-year age bins
    assert df.to_numpy().dtype == np.float32


def test_matrix_axes_are_start_ages():
    df = ssd.load(location="Kenya", which="prem2017")
    # prem's 16 five-year bins -> rows/columns labelled 0, 5, ..., 75.
    assert list(df.index) == list(range(0, 80, 5))
    assert list(df.columns) == list(range(0, 80, 5))

    m = ssd.load(location=ssd.list_locations("mistry2021")[0], which="mistry2021")
    assert list(m.index) == list(range(85))          # single-year bins 0..84


def test_mistry_matrix_shape():
    loc = ssd.list_locations("mistry2021")[0]
    df = ssd.load(location=loc, which="mistry2021")
    assert df.shape == (85, 85)          # mistry2021 is 85 single-year age bins


@pytest.mark.parametrize("name", ["Kenya", "kenya", "KENYA", " kenya "])
def test_location_matching_is_case_and_space_insensitive(name):
    a = ssd.load(location=name, which="prem2017")
    b = ssd.load(location="Kenya", which="prem2017")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


def test_spaces_map_to_underscores():
    a = ssd.load(location="united states", which="prem2021")
    b = ssd.load(location="United_States", which="prem2021")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


@pytest.mark.parametrize("alias", ["KE", "KEN", "Republic of Kenya"])
def test_load_accepts_iso_codes_and_official_names(alias):
    a = ssd.load(location=alias, which="prem2017")
    b = ssd.load(location="Kenya", which="prem2017")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


def test_load_accepts_abbreviations():
    a = ssd.load(location="USA", which="prem2021")
    b = ssd.load(location="United_States", which="prem2021")
    assert np.array_equal(a.to_numpy(), b.to_numpy())


def test_kinds_differ_and_all_are_loadable():
    mats = {k: ssd.load("Kenya", which="prem2017", kind=k).to_numpy()
            for k in ("all", "home", "work", "school", "community")}
    # The combined matrix should differ from at least one component layer.
    assert any(not np.array_equal(mats["all"], mats[k])
               for k in ("home", "work", "school", "community"))


def test_unknown_dataset_raises_valueerror():
    with pytest.raises(ValueError):
        ssd.load("Kenya", which="does_not_exist")


def test_bad_kind_raises_valueerror():
    with pytest.raises(ValueError):
        ssd.load("Kenya", which="prem2017", kind="bogus")


def test_unknown_location_raises_keyerror():
    with pytest.raises(KeyError):
        ssd.load("Atlantis", which="prem2017")


def test_location_absent_from_dataset_raises_keyerror():
    # Kenya exists in prem2017 but not in mistry2021's smaller country set.
    assert "Kenya" not in ssd.list_locations("mistry2021")
    with pytest.raises(KeyError):
        ssd.load("Kenya", which="mistry2021")
