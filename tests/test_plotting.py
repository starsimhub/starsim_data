"""
Test the validation plots. The Agg backend is set in conftest.py.
"""

import matplotlib.pyplot as plt
import sciris as sc
import pytest

import starsim_data as ssd

sc.options(interactive=False) # Assume not running interactively


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def visible(fig):
    """ The axes of a figure that are shown """
    return [ax for ax in fig.axes if ax.get_visible()]


def titled(fig):
    """ The visible axes that have a title: a contact-matrix panel adds a colorbar axis, which does not """
    return [ax for ax in visible(fig) if ax.get_title()]


@sc.timer()
def test_summary():
    """ The summary draws a panel per dataset, and skips what the location lacks """
    sc.heading("Testing the summary figure")
    fig = ssd.plot("kenya")
    titles = [ax.get_title() for ax in visible(fig)]
    for name in ("population", "births", "deaths", "prem"):
        assert any(t.startswith(name) for t in titles), f"no {name} panel in {titles}"

    # Kenya has no mistry2021; a summary should quietly omit it rather than fail
    assert "Kenya" not in ssd.list_locations("mistry2021") # The premise of the next check
    assert all("mistry2021" not in t for t in titles) # Omitted

    # The summary is about demography and contacts; a one-point map adds nothing
    assert all("nodes" not in ax.get_title() for ax in fig.axes) # No node map
    return fig


@sc.timer()
def test_single():
    """ One panel per dataset asked for, and fig_kw is passed through """
    sc.heading("Testing single-dataset plots")
    for which in ["population", "births", "migration", "deaths", "prem2021"]:
        fig = ssd.plot("kenya", which=which)
        assert len(titled(fig)) == 1, f"Expected one panel for {which}"
        plt.close(fig)

    fig = ssd.plot("kenya", which=["population", "deaths"])
    assert len(titled(fig)) == 2 # Two datasets, two panels

    small = ssd.plot("kenya", which="births", fig_kw=dict(figsize=(3, 2)))
    assert tuple(small.get_size_inches()) == (3, 2) # fig_kw reaches the figure
    return fig


@sc.timer()
def test_pyramid():
    """ The population pyramid: both sexes, centred, and a sensible year """
    sc.heading("Testing the population pyramid")
    fig = ssd.plot("kenya", which="population")
    ax = fig.axes[0]
    assert {t.get_text() for t in ax.get_legend().get_texts()} == {"Female", "Male"} # Both sexes
    left, right = ax.get_xlim()
    assert left < 0 < right # Females plotted negative, males positive
    year = int(ax.get_title().split(", ")[-1])
    assert year <= sc.now().year # The default year is an estimate, not a projection

    assert ssd.plot("kenya", which="population", year=2100).axes[0].get_title().endswith("2100") # The year can be overridden
    assert ssd.plot("KEN", which="population").axes[0].get_title().startswith("Kenya") # The title uses the canonical location
    with pytest.raises(ValueError, match="no population data for 1949"): # An unavailable year is reported
        ssd.plot("kenya", which="population", year=1949)
    return fig


@sc.timer()
def test_node_plot():
    """ `plot(which='nodes')` is the map you can draw without the [spatial] extra """
    sc.heading("Testing the node plot")
    fig = ssd.plot("kenya", which="nodes", level=1)
    ax = fig.axes[0]
    assert "47 node(s)" in ax.get_title() # One point per county
    assert ax.collections # Something actually got drawn

    country = ssd.plot("kenya", which="nodes", level=0)
    assert "1 node(s)" in country.axes[0].get_title() # Level 0 is the country
    return fig


@sc.timer()
def test_errors():
    """ Datasets that cannot be plotted, and locations that do not exist, are reported """
    sc.heading("Testing plotting errors")
    with pytest.raises(ValueError, match="cannot plot 'life_table'"): # Tier-1 datasets are not plottable
        ssd.plot("kenya", which="life_table")
    with pytest.raises(ValueError, match="cannot plot"): # Nor are unknown ones
        ssd.plot("kenya", which="not_a_dataset")

    # Unlike a summary, naming a dataset the location lacks is an error
    assert "Japan" not in ssd.list_locations("prem2021") # The premise of the next check
    with pytest.raises(KeyError):
        ssd.plot("Japan", which="prem2021")
    with pytest.raises(KeyError): # Unknown location
        ssd.plot("Atlantis")


if __name__ == "__main__":
    do_plot = True
    sc.options(interactive=do_plot)
    T = sc.timer()

    summary = test_summary()
    single  = test_single()
    pyramid = test_pyramid()
    nodes   = test_node_plot()
    test_errors()

    T.toc()

    if do_plot:
        plt.show()
