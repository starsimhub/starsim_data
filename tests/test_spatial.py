"""
Test the [spatial] tier: boundaries, rasters and the choropleth.

The descriptor tests are offline and always run -- the license constraint on GADM in
particular is a property of the code, not of the network. Everything that actually
downloads is marked `network`, and skips if the optional geospatial dependencies are
not installed. The node plot, which needs none of this, is tested in test_plotting.py.
"""

import matplotlib.pyplot as plt
import numpy as np
import sciris as sc
import pytest

import starsim_data as ssd

geopandas = pytest.importorskip("geopandas", reason="needs the [spatial] extra")


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


# %% Offline

@sc.timer()
def test_sources():
    """ The boundary sources, their terms, and the order they are tried in """
    sc.heading("Testing the boundary sources")
    sources = ssd.list_shape_sources().set_index("source")
    assert set(sources.index) == {"unocha", "geoboundaries", "gadm"} # Every source is listed
    assert set(sources.columns) == {"max_level", "license", "redistributable", "universal", "note"} # With its terms

    # GADM is non-commercial only. The constraint has to be data, not a comment.
    assert ssd.shapes.SOURCES.gadm.redistributable is False # GADM may not be redistributed
    assert ssd.shapes.SOURCES.unocha.redistributable is True # The others may
    assert ssd.shapes.SOURCES.geoboundaries.redistributable is True

    # A non-commercial source must never be reached without the user naming it; UNOCHA
    # goes first, because its p-codes are the join key for subnational health data
    assert "gadm" not in ssd.shapes.FALLBACK_CHAIN # GADM is never a fallback
    assert ssd.shapes.FALLBACK_CHAIN == ("unocha", "geoboundaries") # UNOCHA, then geoBoundaries

    # An unpinned boundary source silently changes the data under a model
    assert ssd.shapes.GEOBOUNDARIES_TAG.startswith("v") # geoBoundaries is pinned to a release tag
    assert f"tags/{ssd.shapes.GEOBOUNDARIES_TAG}" in ssd.shapes.SOURCES.geoboundaries.url # And the URL uses it

    with pytest.raises(ValueError, match="unknown shape source"):
        ssd.fetch_shapes("Kenya", source="not_a_source")
    with pytest.raises(KeyError, match="publishes up to level"): # A source that stops at level 4 says so, rather than asking for a 404
        ssd.fetch_shapes("Kenya", level=5, source="unocha")
    return sources


@sc.timer()
def test_worldpop():
    """ The WorldPop product is chosen by year, and the default year is the node tables' """
    sc.heading("Testing WorldPop product selection")
    products = {
        2020: "Global_2015_2030", # The newer series wins where they overlap
        2015: "Global_2015_2030",
        2030: "Global_2015_2030",
        2000: "Global_2000_2020",
        2010: "Global_2000_2020",
    }
    for year, expected in products.items():
        assert expected in ssd.rasters._product(year)["url"], f"Expected {expected} for {year}"
    for year in [1999, 2031]:
        with pytest.raises(ValueError, match="2000-2030"):
            ssd.rasters._product(year)

    # Level-0 and level-1 populations should be for the same year, or they cannot be compared
    assert ssd.rasters._default_year() == ssd.provenance("nodes").population_year
    return products


# %% Network

@pytest.mark.network
@sc.timer()
def test_fetch_shapes():
    """ Shapes come from UNOCHA, fall back to geoBoundaries, carry provenance and join to the nodes """
    sc.heading("Testing fetch_shapes")
    gdf = ssd.fetch_shapes("kenya", level=1, verbose=False)
    assert set(gdf.source) == {"unocha"} # Kenya is in the UNOCHA mirror
    assert len(gdf) == 47 # Kenya's counties
    assert list(gdf.columns) == list(ssd.shapes.COLUMNS) # The documented columns
    assert gdf.geometry.is_valid.all() # Valid geometry

    prov = gdf.attrs["provenance"]
    assert prov.license == "CC BY 3.0 IGO" # UNOCHA's license
    assert prov.redistributable is True # Which permits redistribution
    assert prov.tier == 1 # Fetched

    france = ssd.fetch_shapes("France", level=1, verbose=False)
    assert set(france.source) == {"geoboundaries"} # France is not in the UNOCHA mirror, so the chain carries on

    # The bundled node table and the fetched geometry must be the same units
    for location, shapes in {"kenya": gdf, "France": france}.items():
        nodes = ssd.load_nodes(location, level=1)
        assert set(shapes.pcode) == set(nodes.pcode), f"Expected {location}'s shapes and nodes to share p-codes"
        assert set(shapes.dot_name) == set(nodes.dot_name), f"Expected {location}'s shapes and nodes to share dot_names"

    with pytest.raises(ValueError, match="not a column"): # The choropleth checks its column
        ssd.choropleth("kenya", value="no_such_column", shapes=gdf)
    return gdf


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_fetch_nodes():
    """ fetch_nodes() fills in level-1 populations from WorldPop, and they rescale to WPP """
    sc.heading("Testing fetch_nodes")
    pytest.importorskip("rastertoolkit", reason="needs the [spatial] extra")
    nodes = ssd.fetch_nodes("kenya", level=1, verbose=False)
    assert nodes.population.notna().all() # Every county has a population
    assert len(nodes) == 47 # Kenya's counties
    national = ssd.load_nodes("Kenya").population.iloc[0]
    assert 0.9 < nodes.population.sum() / national < 1.1 # WorldPop's constrained estimates run a little under the UN total, but only a little
    assert nodes.loc[nodes.population.idxmax(), "name"] == "Nairobi" # Kenya's most populous county, and its smallest by area

    rescaled = ssd.rescale_to_national(nodes)
    assert np.isclose(rescaled.population.sum(), national) # Rescaling hits the WPP total
    assert "UN WPP" in rescaled.attrs["provenance"].rescaled_to # And says so

    # Our own windowed reader and rastertoolkit sum the same raster to the same total
    raster = ssd.fetch_raster("kenya", verbose=False)
    shapes = ssd.fetch_shapes("kenya", level=1, verbose=False)
    window = ssd.rasters._aggregate_window(raster, shapes, by="pcode")
    toolkit = ssd.aggregate_raster(raster, shapes)
    assert np.isclose(sum(window.values()), sum(toolkit.values()), rtol=1e-3) # Within 0.1%: cells on a border may be assigned differently
    return nodes


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_fetch_level2():
    """ fetch_nodes() builds a level that is not bundled, borders included """
    sc.heading("Testing fetch_nodes at level 2")
    pytest.importorskip("rastertoolkit", reason="needs the [spatial] extra")
    nodes = ssd.fetch_nodes("kenya", level=2, verbose=False)
    assert len(nodes) == 290 # Kenya's sub-counties
    assert (nodes.level == 2).all() # All at level 2
    assert nodes.population.notna().all() # Every one has a population
    assert nodes.lat.notna().all() # And a centroid
    level1 = ssd.load_nodes("kenya", level=1).population.sum()
    assert abs(nodes.population.sum() / level1 - 1) < 0.01 # The same raster, cut finer
    a = ssd.adjacency("kenya", level=2, nodes=nodes) # The borders come with the table
    assert a.shape == (290, 290) # One row and column per sub-county
    assert (a.values == a.values.T).all() # Symmetric
    assert a.values.sum(axis=1).min() >= 1 # Every sub-county has a neighbor
    return nodes


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_choropleth():
    """ The choropleth draws a map of population """
    sc.heading("Testing the choropleth")
    pytest.importorskip("rastertoolkit", reason="needs the [spatial] extra")
    ax = ssd.choropleth("kenya", level=1)
    assert ax.get_title().startswith("Kenya") # Titled with the location
    assert ax.collections # Something actually got drawn
    return ax


if __name__ == "__main__":
    do_network = False # Set to True to also run the tests that download (a few hundred MB)
    import conftest
    conftest.isolate_cache() # pytest does this through conftest.py; a script has to ask

    T = sc.timer()

    sources  = test_sources()
    products = test_worldpop()
    if do_network:
        shapes  = test_fetch_shapes()
        nodes   = test_fetch_nodes()
        level2  = test_fetch_level2()
        choro   = test_choropleth()

    T.toc()
