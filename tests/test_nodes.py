"""
Test the bundled node table, distances and adjacency (all offline)
"""

import numpy as np
import sciris as sc
import pytest

import starsim_data as ssd

COLUMNS = ["nodeid", "location", "iso3", "level", "name", "pcode", "dot_name", "parent",
           "lat", "lon", "area_km2", "population", "source"]


@sc.timer()
def test_schema():
    """ The node table's columns, levels, ids and sources """
    sc.heading("Testing the node table schema")
    nodes = ssd.load_nodes("kenya", level=1)
    assert list(nodes.columns) == COLUMNS # The documented columns, in order
    assert len(nodes) == 47 # Kenya's counties
    assert set(nodes.parent) == {"Kenya"} # Each county links to the country

    country = ssd.load_nodes("kenya")
    assert len(country) == 1 # Level 0 is the country itself
    assert country.dot_name.iloc[0] == "Kenya" # Named as the country
    assert country.parent.iloc[0] == "" # With no parent

    everything = ssd.load("Kenya", which="nodes")
    assert set(everything.level) == {0, 1} # No level means every level
    assert len(everything) == 1 + 47 # The country and its counties

    # nodeid must restart per level, so it indexes into that level's distance matrix
    for level in (0, 1):
        level_nodes = ssd.load_nodes("Kenya", level=level)
        assert list(level_nodes.nodeid) == list(range(len(level_nodes))), f"Expected level {level}'s nodeid to count from 0"

    nigeria = ssd.load_nodes("Nigeria", level=1)
    assert nigeria.pcode.nunique() == len(nigeria) # p-codes are unique within a level

    # Coverage is mixed, so which source answered has to travel with the row
    assert set(nodes.source) == {"unocha"} # Kenya is in the UNOCHA mirror
    assert set(ssd.load_nodes("France", level=1).source) == {"geoboundaries"} # France is not
    return nodes


@sc.timer()
def test_names():
    """ dot_names are hierarchical, canonical, and keep their case but not accents or spaces """
    sc.heading("Testing node names")
    nodes = ssd.load_nodes("kenya", level=1)
    assert (nodes.dot_name.str.startswith("Kenya:")).all() # Hierarchical
    assert "Kenya:Baringo" in set(nodes.dot_name) # Case preserved
    assert ssd.resolve(nodes.dot_name.iloc[0].split(":")[0]) == "Kenya" # The first component is always something load() accepts

    france = ssd.load_nodes("France", level=1)
    assert "France:Ile_de_France" in set(france.dot_name) # Île-de-France survives as a key without an accent or a space

    names = {
        "New York":      "New_York",
        "Île-de-France": "Ile_de_France",
        "Baringo":       "Baringo",
        "KwaZulu-Natal": "KwaZulu_Natal",
    }
    for raw, expected in names.items():
        assert ssd.node_name(raw) == expected, f"Expected {raw!r} to become {expected!r}"
    return nodes


@sc.timer()
def test_geography():
    """ Areas, centroids and coverage are plausible """
    sc.heading("Testing node geography")
    # Kenya is about 580,000 km2; its counties should add up to roughly that
    country = ssd.load_nodes("Kenya").area_km2.iloc[0]
    nodes = ssd.load_nodes("Kenya", level=1)
    assert 560_000 < country < 600_000 # The country's area
    assert np.isclose(country, nodes.area_km2.sum(), rtol=0.01) # The counties add up to it

    assert nodes.lat.between(-5, 5).all() # Kenya straddles the equator
    assert nodes.lon.between(33, 42).all() # And lies between these meridians

    locations = set(ssd.list_locations("nodes"))
    assert len(locations) >= 180 # Most of the world
    assert locations <= set(ssd.list_all_locations()) # No strays
    return nodes


@sc.timer()
def test_population():
    """ Node populations: level 0 from WPP, level 1 from WorldPop """
    sc.heading("Testing node populations")
    country = ssd.load_nodes("Kenya")
    population = ssd.load("Kenya", which="population")
    year = ssd.provenance("nodes").population_year
    expected = population[population.Time == year].Value.sum()
    assert np.isclose(country.population.iloc[0], expected) # Level 0 matches the bundled WPP series

    # Level-1 populations are bundled: WorldPop, summed within each unit when the table was built
    nodes = ssd.load_nodes("kenya", level=1)
    assert nodes.population.notna().all() # Every county has one
    assert (nodes.population > 0).all() # And it is positive
    assert abs(nodes.population.sum() / country.population.iloc[0] - 1) < 0.05 # WorldPop and WPP differ by a percent or two
    return nodes


@sc.timer()
def test_errors():
    """ Unknown locations, unavailable levels and stray arguments are reported """
    sc.heading("Testing node errors")
    with pytest.raises(KeyError): # Unknown location
        ssd.load_nodes("Atlantis")
    with pytest.raises(ValueError, match="no level-2 nodes"): # A level that is not bundled
        ssd.load_nodes("Kenya", level=2)
    with pytest.raises(ValueError, match="does not apply"): # level means nothing to other datasets
        ssd.load("Kenya", which="deaths", level=1)


@sc.timer()
def test_distances():
    """ The distance matrix is a proper metric, and gets Nairobi to Mombasa right """
    sc.heading("Testing distances")
    d = ssd.distances("kenya", level=1)
    matrix = d.to_numpy()
    assert d.shape == (47, 47) # One row and column per county
    assert np.allclose(matrix, matrix.T) # Symmetric
    assert np.allclose(np.diag(matrix), 0) # Zero on the diagonal
    assert (matrix >= 0).all() # Non-negative

    # Nairobi to Mombasa is about 440 km as the crow flies, county centroid to centroid
    assert 400 < d.loc["Kenya:Nairobi", "Kenya:Mombasa"] < 480

    # A sanity check on the haversine implementation, not on the data
    direct = matrix[:, :, None]
    via = matrix[:, None, :] + matrix[None, :, :].transpose(0, 2, 1)
    assert (direct <= via + 1e-6).all() # The triangle inequality holds
    return d


@sc.timer()
def test_distance_options():
    """ Units, index and a supplied table, and bad values for them """
    sc.heading("Testing distance options")
    km = ssd.distances("Kenya", level=1)
    miles = ssd.distances("Kenya", level=1, units="mi")
    assert np.allclose(miles.to_numpy(), km.to_numpy() * 0.621371) # Miles are miles

    d = ssd.distances("Kenya", level=1, index="pcode")
    assert "KE047" in d.index # Nairobi's p-code

    nodes = ssd.load_nodes("Kenya", level=1).head(5)
    assert ssd.distances(nodes=nodes).shape == (5, 5) # A supplied table is used as given

    with pytest.raises(ValueError, match="units"):
        ssd.distances("Kenya", level=1, units="furlongs")
    with pytest.raises(ValueError, match="index"):
        ssd.distances("Kenya", level=1, index="nope")
    return miles


@sc.timer()
def test_adjacency():
    """ Which counties share a border """
    sc.heading("Testing adjacency")
    a = ssd.adjacency("kenya", level=1)
    assert a.shape == (47, 47) # One row and column per county
    assert (a.values == a.values.T).all() # Symmetric
    assert not np.diag(a.values).any() # No self-loops
    assert a.values.sum(axis=1).min() >= 1 # Every county has a neighbor
    assert a.loc["Kenya:Nairobi", "Kenya:Kiambu"] # Nairobi borders Kiambu
    assert not a.loc["Kenya:Nairobi", "Kenya:Mombasa"] # But not Mombasa

    nodes = ssd.load_nodes("kenya", level=1)
    some = nodes[nodes.name.isin(["Nairobi", "Kiambu", "Mombasa"])]
    sub = ssd.adjacency("kenya", level=1, nodes=some, index="name")
    assert list(sub.index) == list(some.name) # It follows a subset of nodes
    assert sub.loc["Nairobi", "Kiambu"] # With the same borders
    assert not sub.loc["Nairobi", "Mombasa"] # And the same non-borders

    with pytest.raises(ValueError, match="no borders are bundled"): # Beyond the bundled levels
        ssd.adjacency("kenya", level=2, nodes=nodes.assign(level=2))
    return a


if __name__ == "__main__":
    T = sc.timer()

    nodes = test_schema()
    names = test_names()
    geo   = test_geography()
    pop   = test_population()
    test_errors()
    dist  = test_distances()
    opts  = test_distance_options()
    adj   = test_adjacency()

    T.toc()
