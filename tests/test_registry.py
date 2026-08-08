"""Tests for the dataset registry and layout dispatch."""

import pytest

import starsim_data as ssd


def test_registry_covers_every_dataset():
    assert set(ssd.registry.datasets()) == set(ssd.list_datasets())


def test_bundled_datasets_are_tier_0():
    for name in ssd.list_datasets(tier=0):
        assert ssd.registry.dataset(name).tier == 0


def test_descriptor_fields():
    ds = ssd.registry.dataset("deaths")
    assert ds.layout == "mortality"
    assert ds.levels == (0,)
    assert ds.level == 0
    assert ds.license == "CC BY 3.0 IGO"
    assert ds.n_locations == len(ssd.list_locations("deaths"))
    assert ds.revisions == ("2024",)
    assert ds.description


def test_contact_sources_have_no_revisions():
    assert ssd.registry.dataset("prem2017").revisions == ()


def test_unknown_dataset_suggests_alternatives():
    with pytest.raises(ValueError, match="did you mean.*prem2017"):
        ssd.registry.dataset("prem2016")


def test_source_defaults_to_newest_revision():
    ds = ssd.registry.dataset("births")
    assert ds.source().revision == ds.revisions[-1]


def test_source_rejects_a_revision_for_contact_matrices():
    with pytest.raises(ValueError, match="does not apply"):
        ssd.registry.dataset("prem2017").source(2024)


def test_source_rejects_an_unknown_revision():
    with pytest.raises(ValueError, match="unknown revision"):
        ssd.registry.dataset("births").source(1999)


def test_detailed_listing_is_a_frame():
    df = ssd.list_datasets(detailed=True)
    assert set(df.columns) == {"dataset", "description", "layout", "tier", "levels",
                               "locations", "revisions", "license"}
    assert len(df) == len(ssd.list_datasets())


def test_tier_filter():
    assert "life_table" in ssd.list_datasets(tier=1)
    assert "life_table" not in ssd.list_datasets(tier=0)
    assert "prem2017" in ssd.list_datasets(tier=0)


def test_load_refuses_a_tier_2_dataset_and_points_at_fetch():
    """`load` must never reach for the network -- it should say so instead."""
    with pytest.raises(ValueError, match="not bundled.*use fetch"):
        ssd.load("Kenya", which="life_table")


# --- Registration hooks ------------------------------------------------------------ #

def test_register_and_use_a_custom_dataset():
    ds = ssd.registry.Dataset(name="_test_custom", layout="crude", tier=1,
                              loader=lambda location, **kw: f"loaded {location}")
    ssd.registry.register_dataset(ds)
    try:
        assert "_test_custom" in ssd.list_datasets()
        assert ssd.load("Kenya", which="_test_custom") == "loaded Kenya"
    finally:
        ssd.registry.unregister_dataset("_test_custom")
    assert "_test_custom" not in ssd.list_datasets()


def test_registering_a_duplicate_needs_overwrite():
    ds = ssd.registry.Dataset(name="prem2017", layout="matrix")
    with pytest.raises(ValueError, match="already registered"):
        ssd.registry.register_dataset(ds)


def test_register_dataset_type_checked():
    with pytest.raises(TypeError):
        ssd.registry.register_dataset({"name": "nope"})


def test_unregistering_a_bundled_dataset_fails():
    with pytest.raises(KeyError):
        ssd.registry.unregister_dataset("prem2017")


def test_layouts_are_registered_for_every_bundled_dataset():
    for name in ssd.list_datasets(tier=0):
        assert ssd.registry.dataset(name).layout in ssd.registry.LAYOUTS


def test_registering_a_duplicate_layout_needs_overwrite():
    with pytest.raises(ValueError, match="already registered"):
        ssd.registry.register_layout("matrix", lambda *a: None)


def test_get_layout_rejects_the_unknown():
    with pytest.raises(ValueError, match="unrecognized layout"):
        ssd.registry.get_layout("no_such_layout")


def test_refresh_rediscovers():
    """refresh() clears the cache; the same datasets should come back."""
    before = set(ssd.registry.datasets())
    ssd.registry.refresh()
    assert set(ssd.registry.datasets()) == before
