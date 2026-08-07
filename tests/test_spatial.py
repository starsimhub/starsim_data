"""Tests for the [spatial] tier: boundaries, rasters and the choropleth.

The descriptor tests are offline and always run -- the license constraint on GADM in
particular is a property of the code, not of the network. Everything that actually
downloads is marked `network`, and skips if the optional geospatial dependencies are
not installed.
"""

import matplotlib.pyplot as plt
import numpy as np
import pytest

import starsim_data as ssd

geopandas = pytest.importorskip("geopandas", reason="needs the [spatial] extra")


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


# --- Source descriptors (offline) --------------------------------------------------- #

def test_sources_are_listed_with_their_terms():
    sources = ssd.list_shape_sources().set_index("source")
    assert set(sources.index) == {"unocha", "geoboundaries", "gadm"}
    assert set(sources.columns) == {"max_level", "license", "redistributable", "universal",
                                    "note"}


def test_gadm_is_marked_non_redistributable():
    """GADM is non-commercial only. The constraint has to be data, not a comment."""
    assert ssd.shapes.SOURCES.gadm.redistributable is False
    assert ssd.shapes.SOURCES.unocha.redistributable is True
    assert ssd.shapes.SOURCES.geoboundaries.redistributable is True


def test_gadm_is_not_in_the_automatic_fallback_chain():
    """A non-commercial source must never be reached without the user naming it."""
    assert "gadm" not in ssd.shapes.FALLBACK_CHAIN
    assert ssd.shapes.FALLBACK_CHAIN == ("unocha", "geoboundaries")


def test_unocha_is_tried_before_geoboundaries():
    """UNOCHA first, because its p-codes are the join key for subnational health data."""
    assert ssd.shapes.FALLBACK_CHAIN[0] == "unocha"


def test_geoboundaries_is_pinned_to_a_tag():
    """An unpinned boundary source silently changes the data under a model."""
    assert ssd.shapes.GEOBOUNDARIES_TAG.startswith("v")
    assert f"tags/{ssd.shapes.GEOBOUNDARIES_TAG}" in ssd.shapes.SOURCES.geoboundaries.url


def test_unknown_source_raises():
    with pytest.raises(ValueError, match="unknown shape source"):
        ssd.fetch_shapes("Kenya", source="not_a_source")


def test_level_beyond_the_source_is_reported():
    """A source that stops at level 4 should say so, not go and ask for a 404."""
    with pytest.raises(KeyError, match="publishes up to level"):
        ssd.fetch_shapes("Kenya", level=5, source="unocha")


# --- WorldPop product selection (offline) ------------------------------------------- #

@pytest.mark.parametrize("year, expected", [
    (2020, "Global_2015_2030"),      # the newer series wins where they overlap
    (2015, "Global_2015_2030"),
    (2030, "Global_2015_2030"),
    (2000, "Global_2000_2020"),
    (2010, "Global_2000_2020"),
])
def test_worldpop_product_selection(year, expected):
    assert expected in ssd.rasters._product(year)["url"]


@pytest.mark.parametrize("year", [1999, 2031])
def test_worldpop_year_out_of_range(year):
    with pytest.raises(ValueError, match="2000-2030"):
        ssd.rasters._product(year)


def test_raster_year_defaults_to_the_node_tables():
    """Level-0 and level-1 populations should be for the same year, or they cannot be compared."""
    assert ssd.rasters._default_year() == ssd.provenance("nodes").population_year


# --- Downloads ----------------------------------------------------------------------- #

@pytest.mark.network
def test_fetch_shapes_from_unocha():
    gdf = ssd.fetch_shapes("kenya", level=1, verbose=False)
    assert set(gdf.source) == {"unocha"}
    assert len(gdf) == 47
    assert list(gdf.columns) == list(ssd.shapes.COLUMNS)
    assert gdf.geometry.is_valid.all()


@pytest.mark.network
def test_fetch_shapes_falls_back_to_geoboundaries():
    """France is not in the UNOCHA mirror, so the chain has to carry on to the next source."""
    gdf = ssd.fetch_shapes("France", level=1, verbose=False)
    assert set(gdf.source) == {"geoboundaries"}


@pytest.mark.network
def test_shapes_join_to_nodes_on_pcode():
    """The bundled node table and the fetched geometry must be the same units."""
    for location in ("kenya", "France"):
        gdf = ssd.fetch_shapes(location, level=1, verbose=False)
        nodes = ssd.load_nodes(location, level=1)
        assert set(gdf.pcode) == set(nodes.pcode)
        assert set(gdf.dot_name) == set(nodes.dot_name)


@pytest.mark.network
def test_fetch_shapes_carries_provenance():
    gdf = ssd.fetch_shapes("kenya", level=1, verbose=False)
    prov = gdf.attrs["provenance"]
    assert prov.license == "CC BY 3.0 IGO"
    assert prov.redistributable is True
    assert prov.tier == 2


@pytest.mark.network
@pytest.mark.slow
def test_fetch_nodes_fills_population():
    pytest.importorskip("rastertoolkit", reason="needs the [spatial] extra")
    nodes = ssd.fetch_nodes("kenya", level=1, verbose=False)
    assert nodes.population.notna().all()
    assert len(nodes) == 47
    # WorldPop's constrained estimates run a little under the UN total, but only a little.
    national = ssd.load_nodes("Kenya").population.iloc[0]
    assert 0.9 < nodes.population.sum() / national < 1.1
    # Nairobi is Kenya's most populous county and its smallest by area.
    assert nodes.loc[nodes.population.idxmax(), "name"] == "Nairobi"


@pytest.mark.network
@pytest.mark.slow
def test_rescale_to_national_hits_the_wpp_total():
    pytest.importorskip("rastertoolkit", reason="needs the [spatial] extra")
    nodes = ssd.rescale_to_national(ssd.fetch_nodes("kenya", level=1, verbose=False))
    national = ssd.load_nodes("Kenya").population.iloc[0]
    assert np.isclose(nodes.population.sum(), national)
    assert "UN WPP" in nodes.attrs["provenance"].rescaled_to


@pytest.mark.network
@pytest.mark.slow
def test_choropleth_draws():
    pytest.importorskip("rastertoolkit", reason="needs the [spatial] extra")
    ax = ssd.choropleth("kenya", level=1)
    assert ax.get_title().startswith("Kenya")
    assert ax.collections                        # something actually got drawn


@pytest.mark.network
def test_choropleth_rejects_a_missing_column():
    gdf = ssd.fetch_shapes("kenya", level=1, verbose=False)
    with pytest.raises(ValueError, match="not a column"):
        ssd.choropleth("kenya", value="no_such_column", shapes=gdf)


# --- The offline node plot ----------------------------------------------------------- #

def test_node_plot_needs_no_geometry():
    """`plot(which='nodes')` is the map you can draw without the [spatial] extra."""
    fig = ssd.plot("kenya", which="nodes", level=1)
    ax = fig.axes[0]
    assert "47 node(s)" in ax.get_title()
    assert ax.collections


def test_node_plot_at_level_0():
    fig = ssd.plot("kenya", which="nodes", level=0)
    assert "1 node(s)" in fig.axes[0].get_title()


def test_nodes_are_not_in_the_summary_figure():
    """The summary is about demography and contacts; a one-point map adds nothing."""
    fig = ssd.plot("kenya")
    assert all("nodes" not in ax.get_title() for ax in fig.axes)
