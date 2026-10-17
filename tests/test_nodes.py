"""Tests for the bundled node table and the distance matrix. All offline."""

import numpy as np
import pytest

import starsim_data as ssd

COLUMNS = ["nodeid", "location", "iso3", "level", "name", "pcode", "dot_name", "parent",
           "lat", "lon", "area_km2", "population", "source"]


def test_schema():
    nodes = ssd.load_nodes("kenya", level=1)
    assert list(nodes.columns) == COLUMNS
    assert len(nodes) == 47                        # Kenya's counties


def test_level_0_is_the_country_itself():
    nodes = ssd.load_nodes("kenya")
    assert len(nodes) == 1
    assert nodes.dot_name.iloc[0] == "Kenya"
    assert nodes.parent.iloc[0] == ""


def test_no_level_returns_every_level():
    everything = ssd.load("Kenya", which="nodes")
    assert set(everything.level) == {0, 1}
    assert len(everything) == 1 + 47


def test_nodeid_indexes_the_level():
    """nodeid must restart per level, so it indexes into that level's distance matrix."""
    for level in (0, 1):
        nodes = ssd.load_nodes("Kenya", level=level)
        assert list(nodes.nodeid) == list(range(len(nodes)))


def test_dot_names_are_hierarchical_and_canonical():
    nodes = ssd.load_nodes("kenya", level=1)
    assert (nodes.dot_name.str.startswith("Kenya:")).all()
    assert "Kenya:Baringo" in set(nodes.dot_name)                  # case preserved
    # The first component is always something `load()` accepts.
    assert ssd.resolve(nodes.dot_name.iloc[0].split(":")[0]) == "Kenya"


def test_dot_names_fold_accents_and_spaces():
    """`Île-de-France` has to survive as a key without an accent or a space in it."""
    nodes = ssd.load_nodes("France", level=1)
    assert "France:Ile_de_France" in set(nodes.dot_name)


@pytest.mark.parametrize("raw, expected", [
    ("New York", "New_York"),
    ("Île-de-France", "Ile_de_France"),
    ("Baringo", "Baringo"),
    ("KwaZulu-Natal", "KwaZulu_Natal"),
])
def test_node_name(raw, expected):
    assert ssd.node_name(raw) == expected


def test_parent_links_to_the_country():
    nodes = ssd.load_nodes("kenya", level=1)
    assert set(nodes.parent) == {"Kenya"}


def test_pcodes_are_unique_within_a_level():
    nodes = ssd.load_nodes("Nigeria", level=1)
    assert nodes.pcode.nunique() == len(nodes)


def test_source_is_recorded():
    """Coverage is mixed, so which source answered has to travel with the row."""
    assert set(ssd.load_nodes("Kenya", level=1).source) == {"unocha"}
    assert set(ssd.load_nodes("France", level=1).source) == {"geoboundaries"}


def test_areas_are_plausible():
    """Kenya is about 580,000 km2; its counties should add up to roughly that."""
    country = ssd.load_nodes("Kenya").area_km2.iloc[0]
    counties = ssd.load_nodes("Kenya", level=1).area_km2.sum()
    assert 560_000 < country < 600_000
    assert np.isclose(country, counties, rtol=0.01)


def test_centroids_are_inside_the_bounding_box():
    nodes = ssd.load_nodes("Kenya", level=1)
    assert nodes.lat.between(-5, 5).all()          # Kenya straddles the equator
    assert nodes.lon.between(33, 42).all()


def test_national_population_matches_the_bundled_series():
    nodes = ssd.load_nodes("Kenya")
    population = ssd.load("Kenya", which="population")
    year = ssd.provenance("nodes").population_year
    expected = population[population.Time == year].Value.sum()
    assert np.isclose(nodes.population.iloc[0], expected)


def test_coverage():
    nodes_locations = set(ssd.list_locations("nodes"))
    assert len(nodes_locations) >= 180
    assert nodes_locations <= set(ssd.list_all_locations())        # no strays


def test_unknown_location_raises():
    with pytest.raises(KeyError):
        ssd.load_nodes("Atlantis")


def test_unavailable_level_raises():
    with pytest.raises(ValueError, match="no level-2 nodes"):
        ssd.load_nodes("Kenya", level=2)


def test_level_is_rejected_for_other_datasets():
    with pytest.raises(ValueError, match="does not apply"):
        ssd.load("Kenya", which="deaths", level=1)


# --- distances --------------------------------------------------------------------- #

def test_distance_matrix_properties():
    d = ssd.distances("kenya", level=1)
    assert d.shape == (47, 47)
    matrix = d.to_numpy()
    assert np.allclose(matrix, matrix.T)                   # symmetric
    assert np.allclose(np.diag(matrix), 0)                 # zero on the diagonal
    assert (matrix >= 0).all()


def test_distances_are_right():
    """Nairobi to Mombasa is about 440 km as the crow flies, county centroid to centroid."""
    d = ssd.distances("kenya", level=1)
    assert 400 < d.loc["Kenya:Nairobi", "Kenya:Mombasa"] < 480


def test_distance_units():
    km = ssd.distances("Kenya", level=1)
    miles = ssd.distances("Kenya", level=1, units="mi")
    assert np.allclose(miles.to_numpy(), km.to_numpy() * 0.621371)


def test_distance_index():
    d = ssd.distances("Kenya", level=1, index="pcode")
    assert "KE047" in d.index                              # Nairobi's p-code


def test_distances_accept_a_supplied_table():
    nodes = ssd.load_nodes("Kenya", level=1).head(5)
    d = ssd.distances(nodes=nodes)
    assert d.shape == (5, 5)


def test_distances_reject_bad_arguments():
    with pytest.raises(ValueError, match="units"):
        ssd.distances("Kenya", level=1, units="furlongs")
    with pytest.raises(ValueError, match="index"):
        ssd.distances("Kenya", level=1, index="nope")


def test_triangle_inequality_holds():
    """A sanity check on the haversine implementation, not on the data."""
    d = ssd.distances("Kenya", level=1).to_numpy()
    direct = d[:, :, None]
    via = d[:, None, :] + d[None, :, :].transpose(0, 2, 1)
    assert (direct <= via + 1e-6).all()


def test_level_1_has_populations():
    """Level-1 populations are bundled: WorldPop, summed within each unit when the table was built."""
    nodes = ssd.load_nodes("kenya", level=1)
    assert nodes.population.notna().all() and (nodes.population > 0).all()
    national = ssd.load_nodes("kenya").population.iloc[0]
    assert abs(nodes.population.sum() / national - 1) < 0.05     # WorldPop and WPP differ by a percent or two


def test_adjacency_is_symmetric_with_no_self_loops():
    a = ssd.adjacency("kenya", level=1)
    assert a.shape == (47, 47)
    assert (a.values == a.values.T).all() and not np.diag(a.values).any()
    assert a.values.sum(axis=1).min() >= 1                      # every county has a neighbour


def test_adjacency_has_the_right_neighbours():
    a = ssd.adjacency("kenya", level=1)
    assert a.loc["Kenya:Nairobi", "Kenya:Kiambu"]
    assert not a.loc["Kenya:Nairobi", "Kenya:Mombasa"]


def test_adjacency_follows_a_subset_of_nodes():
    nodes = ssd.load_nodes("kenya", level=1)
    some = nodes[nodes.name.isin(["Nairobi", "Kiambu", "Mombasa"])]
    a = ssd.adjacency("kenya", level=1, nodes=some, index="name")
    assert list(a.index) == list(some.name)
    assert a.loc["Nairobi", "Kiambu"] and not a.loc["Nairobi", "Mombasa"]


def test_adjacency_beyond_the_bundled_levels_raises():
    with pytest.raises(ValueError, match="no borders are bundled"):
        ssd.adjacency("kenya", level=2, nodes=ssd.load_nodes("kenya", level=1).assign(level=2))
