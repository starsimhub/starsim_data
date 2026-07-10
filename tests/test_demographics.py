"""End-to-end test of the WPP demographics pipeline (build_demographics -> load).

Uses tiny synthetic WPP-format CSVs so the build + load plumbing is verified without
the real (large) UN files, and writes to a temp dir so the shipped package data is
untouched.
"""

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_demographics as bd  # noqa: E402

# `starsim_data.load` the submodule is shadowed by the re-exported `load` function,
# so grab the module object explicitly.
ssload = importlib.import_module("starsim_data.load")

YEARS = bd.YEARS
AGES_MX = [0, 1, 5, 10]
AGES_POP = ["0", "1", "2", "100+"]


def _write_synthetic_wpp(wpp_dir):
    """Create minimal indicators / life-table / population CSVs for Kenya (KE) & US."""
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


@pytest.fixture
def built(tmp_path, monkeypatch):
    """Build the four demographic stores into a temp dir and point the loader at it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(bd, "OUT", data_dir)
    monkeypatch.setattr(ssload, "_data_dir", lambda: data_dir)

    _write_synthetic_wpp(tmp_path / "wpp")
    bd.build(tmp_path / "wpp")
    return data_dir


def test_datasets_built(built):
    assert set(ssload.list_datasets()) == {"births", "migration", "deaths", "population"}


def test_births_shape_and_columns(built):
    df = ssload.load("kenya", which="births")
    assert list(df.columns) == ["Time", "CBR"]
    assert len(df) == len(YEARS)
    assert df["Time"].tolist() == YEARS


def test_migration_columns(built):
    df = ssload.load("United_States", which="migration")
    assert list(df.columns) == ["Time", "CNMR"]
    assert len(df) == len(YEARS)


def test_deaths_is_starsim_ready(built):
    df = ssload.load("Kenya", which="deaths")
    # Column names match ss.Deaths default metadata (data_cols year=Time, sex, age, value=mx).
    assert list(df.columns) == ["Time", "Sex", "AgeGrpStart", "mx"]
    assert set(df["Sex"]) == {"Female", "Male"}      # "Total" dropped
    assert set(df["AgeGrpStart"]) == set(AGES_MX)
    assert len(df) == len(YEARS) * 2 * len(AGES_MX)
    assert df["mx"].notna().all()


def test_population_single_age_and_plus_bin(built):
    df = ssload.load("Kenya", which="population")
    assert list(df.columns) == ["Time", "Sex", "AgeGrp", "Value"]
    assert 100 in set(df["AgeGrp"])                  # "100+" parsed to 100
    assert set(df["Sex"]) == {"Female", "Male"}


def test_value_roundtrip(built):
    # A known mx value: Kenya (i=0), any year, Female, age 5 -> 0.001*(5+1) + 0 = 0.006
    df = ssload.load("Kenya", which="deaths")
    row = df[(df.Time == YEARS[0]) & (df.Sex == "Female") & (df.AgeGrpStart == 5)]
    assert np.isclose(row["mx"].iloc[0], 0.006)
