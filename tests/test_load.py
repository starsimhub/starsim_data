"""
Test the loader: contact matrices, location matching and error paths
"""

import hashlib
import tempfile

import h5py
import numpy as np
import pandas as pd
import sciris as sc
import pytest

import starsim_data as ssd

# The contact stores that are fetched rather than bundled, as committed in the repository.
FETCHED = sc.thispath(__file__).parent / "fetched"


@sc.timer()
def test_listing():
    """ Datasets and locations are listed sorted, without duplicates """
    sc.heading("Testing listing")
    datasets = ssd.list_datasets()
    assert "prem2017" in datasets # A fetched source is listed
    assert "prem2021" in datasets # So is a bundled one
    assert datasets == sorted(set(datasets)) # Sorted, with no duplicates
    locs = ssd.list_locations("prem2021")
    assert "Kenya" in locs # Canonical names are listed
    assert locs == sorted(locs) # Sorted
    return datasets


@sc.timer()
def test_matrix():
    """ A contact matrix is a float32 sciris dataframe whose axes are the bin start ages """
    sc.heading("Testing contact matrices")
    df = ssd.load(location="Kenya", which="prem2021")
    assert isinstance(df, sc.dataframe) # A drop-in replacement for a pandas DataFrame
    assert isinstance(df, pd.DataFrame) # ...which is still a pandas DataFrame
    assert df.shape == (16, 16) # Prem sources are 16 five-year age bins
    assert df.to_numpy().dtype == np.float32 # Stored and returned as float32
    assert list(df.index) == list(range(0, 80, 5)) # Rows are labeled 0, 5, ..., 75
    assert list(df.columns) == list(range(0, 80, 5)) # So are the columns

    m = ssd.fetch(location=ssd.list_locations("mistry2021")[0], which="mistry2021")
    assert m.shape == (85, 85) # mistry2021 is 85 single-year age bins
    assert list(m.index) == list(range(85)) # Labeled 0..84
    return df


@sc.timer()
def test_location_names():
    """ Any spelling, code or alias of a location loads the same matrix """
    sc.heading("Testing location matching")
    names = {
        "Kenya":         ["Kenya", "kenya", "KENYA", " kenya ", "KE", "KEN", "Republic of Kenya"],
        "United_States": ["united states", "USA"],
    }
    for canonical, aliases in names.items():
        expected = ssd.load(location=canonical, which="prem2021").to_numpy()
        for alias in aliases:
            got = ssd.load(location=alias, which="prem2021").to_numpy()
            assert np.array_equal(got, expected), f"Expected {alias!r} to load the same matrix as {canonical!r}"
    return names


@sc.timer()
def test_kinds():
    """ Every setting is loadable, and the combined matrix is not just one of them """
    sc.heading("Testing contact settings")
    kinds = ("all", "home", "work", "school", "community")
    mats = {kind: ssd.load("Kenya", which="prem2021", kind=kind).to_numpy() for kind in kinds}
    differ = [not np.array_equal(mats["all"], mats[kind]) for kind in kinds[1:]]
    assert any(differ) # The combined matrix differs from at least one component layer
    return mats


@sc.timer()
def test_default_contacts():
    """ The default contact source is prem2021, falling back to prem2017 """
    sc.heading("Testing the default contact source")
    assert ssd.load("Kenya").equals(ssd.load("Kenya", which="prem2021")) # prem2021 where it has the location
    japan = ssd.load("Japan", kind="home")
    assert japan.attrs["dataset"] == "prem2017" # prem2017 for the ten locations it lacks
    assert len(ssd.list_locations("prem")) == 187 # The union of the two
    return japan


@sc.timer()
def test_errors():
    """ Bad datasets, settings, locations and arguments are reported """
    sc.heading("Testing loader errors")
    with pytest.raises(ValueError): # Unknown dataset
        ssd.load("Kenya", which="does_not_exist")
    with pytest.raises(ValueError): # Unknown setting
        ssd.load("Kenya", which="prem2021", kind="bogus")
    with pytest.raises(KeyError): # Unknown location
        ssd.load("Atlantis", which="prem2021")

    # Kenya exists in prem2021 but not in mistry2021's smaller country set
    assert "Kenya" not in ssd.list_locations("mistry2021") # The premise of the next check
    with pytest.raises(KeyError): # A real location the dataset lacks
        ssd.fetch("Kenya", which="mistry2021")

    # A location missing from prem2021 points at the sources that have it
    with pytest.raises(KeyError, match=r"load\('Japan'\) or fetch\('Japan', which='mistry2021'\) or fetch\('Japan', which='prem2017'\)"):
        ssd.load("Japan", which="prem2021")

    # An argument a dataset has no use for is rejected, not ignored
    with pytest.raises(ValueError, match="does not apply"):
        ssd.fetch("France", which="prem2017", years=2020)
    with pytest.raises(ValueError, match="does not apply"):
        ssd.fetch("Kenya", which="deaths", kind="home")


@sc.timer()
def test_fetched_contacts():
    """ The contact sources that are not bundled are tier 1: listed, and fetched as load() reads """
    sc.heading("Testing fetched contact sources")
    for which in ["prem2017", "mistry2021"]:
        ds = ssd.registry.dataset(which)
        assert ds.tier == 1, f"Expected {which} to be tier 1"
        assert which in ssd.list_fetchable(), f"Expected {which} to be fetchable"
        with pytest.raises(ValueError, match="not bundled.*use fetch"): # load() refuses, and names fetch()
            ssd.load("France", which=which)
        df = ssd.fetch("France", which=which, kind="home")
        assert df.attrs["dataset"] == which, f"Expected {which} to record its dataset"
        assert df.attrs["provenance"].tier == 1, f"Expected {which} to record tier 1"
        assert len(ssd.list_locations(which)) == ds.n_locations, f"Expected {which} to list as many locations as its descriptor says"
    return df


@sc.timer()
def test_manifest():
    """ The digest fetch() checks must be that of the store in fetched/, or a download would be refused """
    sc.heading("Testing the fetched-store manifest")
    for name in ("prem2017", "mistry2021"):
        source = ssd.registry.dataset(name).source()
        digest = hashlib.sha256((FETCHED / source.store).read_bytes()).hexdigest()
        assert digest == source.sha256, f"Expected fetched/{source.store} to match the manifest"
    return source


@pytest.mark.network
@sc.timer()
def test_pinned_download(tmp_path):
    """ The pinned URL serves the bytes the manifest records, and fetch() reads them """
    sc.heading("Testing downloading the pinned stores")
    for which in ["prem2017", "mistry2021"]:
        with ssd.options.context(cache_dir=str(tmp_path / which)): # A cache of its own, without the seeded copies
            df = ssd.fetch("France", which=which, verbose=False)
        assert df.attrs["provenance"].files[0]["sha256"] == ssd.registry.dataset(which).source().sha256, f"Expected the {which} download to match the manifest"
        with h5py.File(FETCHED / f"{which}.h5", "r") as f:
            assert np.array_equal(df.to_numpy(), f["France/all"][:]), f"Expected the {which} download to match the committed store"
    return df


if __name__ == "__main__":
    do_network = False # Set to True to also run the tests that download
    import conftest
    conftest.isolate_cache() # pytest does this through conftest.py; a script has to ask

    T = sc.timer()

    listing  = test_listing()
    matrix   = test_matrix()
    names    = test_location_names()
    kinds    = test_kinds()
    default  = test_default_contacts()
    errors   = test_errors()
    fetched  = test_fetched_contacts()
    manifest = test_manifest()
    if do_network:
        pinned = test_pinned_download(sc.path(tempfile.mkdtemp()))

    T.toc()
