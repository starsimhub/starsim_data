"""
Test that the bundled demographic stores (the real shipped data) are present and sane.

The pipeline itself is tested with synthetic inputs in test_demographics.py; these
tests assert the actual UN WPP data that ships in the package is present and sane.
"""

import sciris as sc
import pytest

import starsim_data as ssd

DEMOGRAPHIC = ["births", "deaths", "migration", "population"]


@sc.timer()
def test_births():
    """ Births and migration are crude series, and fertility is ordered as expected """
    sc.heading("Testing births and migration")
    assert set(DEMOGRAPHIC) <= set(ssd.list_datasets()) # Every demographic dataset is present

    b = ssd.load("Kenya", which="births")
    assert list(b.columns) == ["Time", "CBR"] # Crude birth rate by year
    assert b["Time"].tolist() == list(range(1950, 2101, 10)) # Every decade from 1950 to 2100
    m = ssd.load("Kenya", which="migration")
    assert list(m.columns) == ["Time", "CNMR"] # Crude net migration rate by year

    # Niger has among the highest fertility in the world; Japan among the lowest
    ne = ssd.load("Niger", which="births")
    jp = ssd.load("Japan", which="births")
    ne_cbr = float(ne.loc[ne.Time == 2020, "CBR"].iloc[0])
    jp_cbr = float(jp.loc[jp.Time == 2020, "CBR"].iloc[0])
    assert ne_cbr > 30 # High fertility
    assert jp_cbr < 30 # Low fertility

    with pytest.raises(KeyError): # Unknown location
        ssd.load("Atlantis", which="births")
    return b


@sc.timer()
def test_deaths():
    """ Death rates are Starsim-ready and J-shaped """
    sc.heading("Testing deaths")
    d = ssd.load("Kenya", which="deaths")
    assert list(d.columns) == ["Time", "Sex", "AgeGrpStart", "mx"] # Starsim-ready
    assert set(d["Sex"]) == {"Female", "Male"} # Both sexes, no total
    assert (d["mx"] >= 0).all() # Rates are non-negative
    assert d["mx"].notna().all() # And present
    # Classic mortality curve: elevated in infancy, low in childhood, rising into old age
    f2020 = d[(d.Time == 2020) & (d.Sex == "Female")].set_index("AgeGrpStart")["mx"]
    assert f2020.loc[0] > f2020.loc[10] # Infancy above childhood
    assert f2020.loc[85] > f2020.loc[40] # Old age above middle age
    return d


@sc.timer()
def test_population():
    """ Population is in absolute persons, in 5-year bins """
    sc.heading("Testing population")
    p = ssd.load("Kenya", which="population")
    assert list(p.columns) == ["Time", "Sex", "AgeGrp", "Value"] # Starsim-ready
    assert p["AgeGrp"].max() == 100 # 5-year bins 0..100
    assert 5 in set(p["AgeGrp"]) # Ditto
    total_2020 = p.loc[p.Time == 2020, "Value"].sum()
    assert 45e6 < total_2020 < 60e6 # Kenya 2020 ≈ 52M, in absolute persons
    return p


if __name__ == "__main__":
    T = sc.timer()

    births = test_births()
    deaths = test_deaths()
    pop    = test_population()

    T.toc()
