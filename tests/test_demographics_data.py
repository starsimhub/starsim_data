"""Sanity checks on the bundled demographic stores (the real shipped data).

The pipeline itself is tested with synthetic inputs in test_demographics.py; these
tests assert the actual UN WPP data that ships in the package is present and sane.
"""

import numpy as np
import pytest

import starsim_data as ssd

DEMOGRAPHIC = ["births", "deaths", "migration", "population"]


def test_demographic_datasets_present():
    assert set(DEMOGRAPHIC) <= set(ssd.list_datasets())


def test_births_and_migration_are_crude_series():
    b = ssd.load("Kenya", which="births")
    assert list(b.columns) == ["Time", "CBR"]
    assert b["Time"].tolist() == list(range(1950, 2101, 10))
    m = ssd.load("Kenya", which="migration")
    assert list(m.columns) == ["Time", "CNMR"]


def test_births_ordering_high_vs_low_fertility():
    # Niger has among the highest fertility in the world; Japan among the lowest.
    ne = ssd.load("Niger", which="births")
    jp = ssd.load("Japan", which="births")
    at = lambda df: float(df.loc[df.Time == 2020, "CBR"].iloc[0])
    assert at(ne) > 30 > at(jp)


def test_deaths_is_starsim_ready_and_j_shaped():
    d = ssd.load("Kenya", which="deaths")
    assert list(d.columns) == ["Time", "Sex", "AgeGrpStart", "mx"]
    assert set(d["Sex"]) == {"Female", "Male"}
    assert (d["mx"] >= 0).all() and d["mx"].notna().all()
    f2020 = d[(d.Time == 2020) & (d.Sex == "Female")].set_index("AgeGrpStart")["mx"]
    # Classic mortality curve: elevated in infancy, low in childhood, rising into old age.
    assert f2020.loc[0] > f2020.loc[10]
    assert f2020.loc[85] > f2020.loc[40]


def test_population_is_absolute_persons():
    p = ssd.load("Kenya", which="population")
    assert list(p.columns) == ["Time", "Sex", "AgeGrp", "Value"]
    # 5-year bins 0..100
    assert p["AgeGrp"].max() == 100 and 5 in set(p["AgeGrp"])
    total_2020 = p.loc[p.Time == 2020, "Value"].sum()
    assert 45e6 < total_2020 < 60e6      # Kenya 2020 ≈ 52M, in absolute persons


def test_unknown_demographic_location_raises():
    with pytest.raises(KeyError):
        ssd.load("Atlantis", which="births")
