"""
Test the dataset registry and layout dispatch
"""

import sciris as sc
import pytest

import starsim_data as ssd


@sc.timer()
def test_datasets():
    """ The registry lists every dataset, and rediscovers the same ones after a refresh """
    sc.heading("Testing the registry")
    datasets = ssd.registry.datasets()
    assert set(datasets) == set(ssd.list_datasets()) # The registry and the listing agree

    df = ssd.list_datasets(detailed=True)
    assert set(df.columns) == {"dataset", "description", "layout", "tier", "levels", "locations", "revisions", "license"} # The detailed listing is a frame
    assert len(df) == len(ssd.list_datasets()) # With a row per dataset

    ssd.registry.refresh()
    assert set(ssd.registry.datasets()) == set(datasets) # refresh() clears the cache; the same datasets come back
    return df


@sc.timer()
def test_tiers():
    """ Bundled datasets are tier 0, fetched ones tier 1, and load() refuses tier 1 """
    sc.heading("Testing tiers")
    for name in ssd.list_datasets(tier=0):
        assert ssd.registry.dataset(name).tier == 0, f"Expected bundled {name} to be tier 0"
    assert "life_table" in ssd.list_datasets(tier=1) # Fetched
    assert "life_table" not in ssd.list_datasets(tier=0) # Not bundled
    assert "prem2021" in ssd.list_datasets(tier=0) # Bundled
    assert "prem2017" in ssd.list_datasets(tier=1) # Fetched, not bundled
    with pytest.raises(ValueError, match="not bundled.*use fetch"): # load() never reaches for the network; it says so instead
        ssd.load("Kenya", which="life_table")


@sc.timer()
def test_descriptor():
    """ A descriptor's fields, and the error for an unknown name """
    sc.heading("Testing descriptors")
    ds = ssd.registry.dataset("deaths")
    assert ds.layout == "mortality" # How it is shaped
    assert ds.levels == (0,) # National only
    assert ds.level == 0 # Ditto
    assert ds.license == "CC BY 3.0 IGO" # WPP's license
    assert ds.n_locations == len(ssd.list_locations("deaths")) # The count matches the store
    assert ds.revisions == ("2024",) # The WPP revisions bundled
    assert ds.description # Described
    assert ssd.registry.dataset("prem2017").revisions == () # Contact sources have no revisions
    with pytest.raises(ValueError, match="did you mean.*prem2017"): # An unknown name suggests alternatives
        ssd.registry.dataset("prem2016")
    return ds


@sc.timer()
def test_source():
    """ A descriptor's source defaults to the newest revision, and checks the one asked for """
    sc.heading("Testing sources")
    ds = ssd.registry.dataset("births")
    assert ds.source().revision == ds.revisions[-1] # The newest by default
    with pytest.raises(ValueError, match="does not apply"): # Contact sources take no revision
        ssd.registry.dataset("prem2017").source(2024)
    with pytest.raises(ValueError, match="unknown revision"):
        ds.source(1999)
    return ds


@sc.timer()
def test_register():
    """ A custom dataset can be registered, used and unregistered; the bundled ones are protected """
    sc.heading("Testing dataset registration")
    ds = ssd.registry.Dataset(name="_test_custom", layout="crude", tier=1, loader=lambda location, **kw: f"loaded {location}")
    ssd.registry.register_dataset(ds)
    try:
        assert "_test_custom" in ssd.list_datasets() # Listed once registered
        assert ssd.load("Kenya", which="_test_custom") == "loaded Kenya" # load() delegates to the loader
    finally:
        ssd.registry.unregister_dataset("_test_custom")
    assert "_test_custom" not in ssd.list_datasets() # Gone once unregistered

    with pytest.raises(ValueError, match="already registered"): # A duplicate needs overwrite
        ssd.registry.register_dataset(ssd.registry.Dataset(name="prem2017", layout="matrix"))
    with pytest.raises(TypeError): # Only a Dataset can be registered
        ssd.registry.register_dataset({"name": "nope"})
    with pytest.raises(KeyError): # A bundled dataset cannot be unregistered
        ssd.registry.unregister_dataset("prem2017")
    return ds


@sc.timer()
def test_layouts():
    """ Every bundled dataset has a layout, and layouts are protected like datasets """
    sc.heading("Testing layouts")
    for name in ssd.list_datasets(tier=0):
        assert ssd.registry.dataset(name).layout in ssd.registry.LAYOUTS, f"Expected {name}'s layout to be registered"
    with pytest.raises(ValueError, match="already registered"): # A duplicate needs overwrite
        ssd.registry.register_layout("matrix", lambda *a: None)
    with pytest.raises(ValueError, match="unrecognized layout"):
        ssd.registry.get_layout("no_such_layout")


if __name__ == "__main__":
    T = sc.timer()

    datasets = test_datasets()
    test_tiers()
    desc     = test_descriptor()
    source   = test_source()
    custom   = test_register()
    test_layouts()

    T.toc()
