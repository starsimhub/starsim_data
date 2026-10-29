"""
Test the WPP demographics pipeline end to end (build_demographics -> load).

Uses tiny synthetic WPP-format CSVs so the build + load plumbing is verified without
the real (large) UN files, and writes to a temp dir so the shipped package data is
untouched.
"""

import sys
import tempfile

import numpy as np
import pandas as pd
import sciris as sc
import pytest

import starsim_data as ssd

sys.path.insert(0, str(sc.thispath(__file__).parent / "scripts"))
import build_demographics as bd # Imported here since it is only importable once scripts/ is on the path

YEARS = bd.YEARS
AGES_MX = [0, 1, 5, 10]
AGES_POP = ["0", "1", "2", "100+"]
AGES_FERT = [15, 20, 45]


def make_wpp(wpp_dir):
    """ Create minimal indicators / life-table / population / fertility CSVs for Kenya (KE) & US """
    wpp_dir.mkdir(parents=True)
    isos = ["KE", "US"]

    ind = [dict(ISO2_code=iso, Time=y, CBR=30 + i + y / 1000, CNMR=(-1) ** i * 2.0)
           for i, iso in enumerate(isos) for y in YEARS]
    pd.DataFrame(ind).to_csv(wpp_dir / "indicators.csv", index=False)

    lt = [dict(ISO2_code=iso, Time=y, Sex=sex, AgeGrpStart=a, mx=0.001 * (a + 1) + 0.0001 * i)
          for i, iso in enumerate(isos) for y in YEARS
          for sex in ("Female", "Male", "Total") for a in AGES_MX]
    pd.DataFrame(lt).to_csv(wpp_dir / "lifetable.csv", index=False)

    pop = [dict(ISO2_code=iso, Time=y, AgeGrp=a, PopMale=100 + j, PopFemale=110 + j)
           for iso in isos for y in YEARS for j, a in enumerate(AGES_POP)]
    pd.DataFrame(pop).to_csv(wpp_dir / "population.csv", index=False)

    fert = [dict(ISO2_code=iso, Time=y, AgeGrpStart=a, ASFR=100.0 + a + i)
            for i, iso in enumerate(isos) for y in YEARS for a in AGES_FERT]
    pd.DataFrame(fert).to_csv(wpp_dir / "fertility.csv", index=False)


@sc.timer()
def test_pipeline(tmp_path, monkeypatch):
    """ Build the five demographic series into a temp dir, point the loader at it, and read them back """
    sc.heading("Testing the demographics pipeline")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(bd, "OUT", data_dir)
    # The registry finds the bundled stores through data_dir() and caches what it finds,
    # so point it at the temp dir and clear the cache on both sides of the test
    monkeypatch.setattr(ssd.registry, "data_dir", lambda: data_dir)
    make_wpp(tmp_path / "wpp")
    bd.build(tmp_path / "wpp")
    ssd.registry.refresh()
    try:
        assert set(ssd.list_datasets(tier=0)) == {"births", "migration", "deaths", "population", "fertility"} # All five series are built

        births = ssd.load("kenya", which="births")
        assert list(births.columns) == ["Time", "CBR"] # Crude birth rate by year
        assert len(births) == len(YEARS) # One row per year
        assert births["Time"].tolist() == YEARS # The years built

        migration = ssd.load("United_States", which="migration")
        assert list(migration.columns) == ["Time", "CNMR"] # Crude net migration rate by year
        assert len(migration) == len(YEARS) # One row per year

        # Column names match ss.Deaths default metadata (data_cols year=Time, sex, age, value=mx)
        deaths = ssd.load("Kenya", which="deaths")
        assert list(deaths.columns) == ["Time", "Sex", "AgeGrpStart", "mx"] # Starsim-ready
        assert set(deaths["Sex"]) == {"Female", "Male"} # "Total" dropped
        assert set(deaths["AgeGrpStart"]) == set(AGES_MX) # Every age group
        assert len(deaths) == len(YEARS) * 2 * len(AGES_MX) # Every year, sex and age
        assert deaths["mx"].notna().all() # No gaps

        # A known mx value: Kenya (i=0), any year, Female, age 5 -> 0.001*(5+1) + 0 = 0.006
        row = deaths[(deaths.Time == YEARS[0]) & (deaths.Sex == "Female") & (deaths.AgeGrpStart == 5)]
        assert np.isclose(row["mx"].iloc[0], 0.006) # Values survive the round trip

        population = ssd.load("Kenya", which="population")
        assert list(population.columns) == ["Time", "Sex", "AgeGrp", "Value"] # Starsim-ready
        assert 100 in set(population["AgeGrp"]) # "100+" parsed to 100
        assert set(population["Sex"]) == {"Female", "Male"} # Both sexes

        fertility = ssd.load("United_States", which="fertility")
        assert list(fertility.columns) == ["Time", "AgeGrpStart", "ASFR"] # Starsim-ready
        assert len(fertility) == len(YEARS) * len(AGES_FERT) # Every year and age
        assert np.isclose(fertility.ASFR.iloc[1], 100 + 20 + 1) # US (i=1), the first year, age 20
    finally:
        ssd.registry.refresh() # Forget the temp stores; they are rediscovered lazily, after the patch is undone
    return deaths


if __name__ == "__main__":
    T = sc.timer()

    with pytest.MonkeyPatch.context() as monkeypatch:
        deaths = test_pipeline(sc.path(tempfile.mkdtemp()), monkeypatch)

    T.toc()
