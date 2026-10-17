"""Tests for the validation plots. The Agg backend is set in conftest.py."""

import matplotlib.pyplot as plt
import pytest

import starsim_data as ssd


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def _visible(fig):
    return [ax for ax in fig.axes if ax.get_visible()]


def test_summary_draws_a_panel_per_dataset():
    fig = ssd.plot("kenya")
    titles = [ax.get_title() for ax in _visible(fig)]
    for name in ("population", "births", "deaths", "prem2021"):
        assert any(t.startswith(name) for t in titles), f"no {name} panel in {titles}"


def test_summary_skips_datasets_the_location_lacks():
    """Kenya has no mistry2021; a summary should quietly omit it rather than fail."""
    assert "Kenya" not in ssd.list_locations("mistry2021")
    fig = ssd.plot("Kenya")
    assert all("mistry2021" not in ax.get_title() for ax in _visible(fig))


@pytest.mark.parametrize("which", ["population", "births", "migration", "deaths", "prem2021"])
def test_single_dataset_gives_one_panel(which):
    fig = ssd.plot("kenya", which=which)
    # A contact-matrix panel adds a colorbar axis, so count the ones with a title.
    assert len([ax for ax in _visible(fig) if ax.get_title()]) == 1


def test_several_datasets():
    fig = ssd.plot("kenya", which=["population", "deaths"])
    assert len([ax for ax in _visible(fig) if ax.get_title()]) == 2


def test_pyramid_has_both_sexes_and_is_centred():
    fig = ssd.plot("kenya", which="population")
    ax = fig.axes[0]
    assert {t.get_text() for t in ax.get_legend().get_texts()} == {"Female", "Male"}
    left, right = ax.get_xlim()
    assert left < 0 < right           # females plotted negative, males positive


def test_default_year_is_not_a_projection():
    """The default panel year should be an estimate, not a forecast."""
    import datetime
    fig = ssd.plot("kenya", which="population")
    year = int(fig.axes[0].get_title().split(", ")[-1])
    assert year <= datetime.date.today().year


def test_year_can_be_overridden():
    fig = ssd.plot("kenya", which="population", year=2100)
    assert fig.axes[0].get_title().endswith("2100")


def test_unavailable_year_is_reported():
    with pytest.raises(ValueError, match="no population data for 1949"):
        ssd.plot("kenya", which="population", year=1949)


def test_title_uses_the_canonical_location():
    fig = ssd.plot("KEN", which="population")
    assert fig.axes[0].get_title().startswith("Kenya")


def test_fig_kw_is_passed_through():
    fig = ssd.plot("kenya", which="births", fig_kw=dict(figsize=(3, 2)))
    assert tuple(fig.get_size_inches()) == (3, 2)


def test_tier_2_datasets_are_not_plottable():
    with pytest.raises(ValueError, match="cannot plot 'life_table'"):
        ssd.plot("kenya", which="life_table")


def test_unknown_dataset_is_reported():
    with pytest.raises(ValueError, match="cannot plot"):
        ssd.plot("kenya", which="not_a_dataset")


def test_explicitly_requested_missing_data_still_raises():
    """Unlike a summary, naming a dataset the location lacks is an error."""
    assert "Japan" not in ssd.list_locations("prem2021")
    with pytest.raises(KeyError):
        ssd.plot("Japan", which="prem2021")


def test_unknown_location_raises():
    with pytest.raises(KeyError):
        ssd.plot("Atlantis")
