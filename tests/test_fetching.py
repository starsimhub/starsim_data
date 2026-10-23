"""
Test fetch().

The tests that actually download are marked `network` and are deselected by default in
CI; the rest run offline. Set `STARSIM_DATA_CACHE_DIR` to reuse the downloads between
runs -- the life-table tests alone pull ~145 MB.
"""

import numpy as np
import sciris as sc
import pytest

import starsim_data as ssd

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# %% Offline

@sc.timer()
def test_fetchable():
    """ The fetchable series are listed and registered as tier 1, and a typo gets suggestions """
    sc.heading("Testing the fetchable series")
    fetchable = ssd.list_fetchable()
    for name in ("births", "deaths", "migration", "population", "life_table", "indicators"):
        assert name in fetchable, f"Expected {name} to be fetchable"
    for name in ("life_table", "indicators"):
        assert ssd.registry.dataset(name).tier == 1, f"Expected fetch-only {name} to be tier 1"
    with pytest.raises(ValueError, match="did you mean.*births"):
        ssd.fetch("Kenya", which="birth")
    return fetchable


@sc.timer()
def test_parse_years():
    """ Years can be one, a range, a list or a range object, and are checked """
    sc.heading("Testing year parsing")
    cases = [
        (None, None),
        (2020, [2020]),
        ((2000, 2003), [2000, 2001, 2002, 2003]), # A 2-tuple is an inclusive range
        ([2000, 2020, 2010], [2000, 2010, 2020]), # A list is exactly those years
        (range(2000, 2003), [2000, 2001, 2002]),
    ]
    for years, expected in cases:
        assert ssd.fetching._parse_years(years) == expected, f"Expected {years!r} to parse to {expected}"
    with pytest.raises(ValueError, match="inclusive"): # A backwards range
        ssd.fetching._parse_years((2020, 2000))
    with pytest.raises(ValueError, match="empty"):
        ssd.fetching._parse_years([])
    return cases


@sc.timer()
def test_files():
    """ Only the files that cover the requested years and variant get downloaded """
    sc.heading("Testing file selection")
    life_table = ssd.fetching.FILES["life_table"]
    cases = [
        (None, 2),         # Both halves
        ([2020], 1),       # Estimates only
        ([2030], 1),       # Projections only
        ([2020, 2030], 2), # Spans the split
    ]
    for years, n_files in cases:
        assert len(life_table.urls("2024", "Medium", years)) == n_files, f"Expected {n_files} life-table file(s) for {years}"
    with pytest.raises(ValueError, match="year split"): # An unknown revision's split is reported
        life_table.urls("2099", "Medium", None)

    medium = ssd.fetching.FILES["indicators"].urls("2024", "Medium", None)
    other = ssd.fetching.FILES["indicators"].urls("2024", "High", None)
    assert "Medium" in list(medium)[0] # The Medium variant has its own file
    assert "OtherVariants" in list(other)[0] # The rest share one

    with pytest.raises(ValueError, match="Medium variant only"): # The UN publishes no non-Medium life table
        ssd.fetch("Kenya", which="deaths", variant="High")
    return cases


# %% Network

@pytest.mark.network
@sc.timer()
def test_fetch_births():
    """ The fetched births match the bundled ones, carry provenance and are cached """
    sc.heading("Testing fetching births")
    fetched = ssd.fetch("kenya", which="births", years=(2018, 2024), verbose=False)
    bundled = ssd.load("Kenya", which="births")
    assert list(fetched.columns) == ["Time", "CBR"] # The bundled schema
    assert fetched.Time.tolist() == list(range(2018, 2025)) # Annual, not decadal
    a = float(fetched[fetched.Time == 2020].CBR.iloc[0])
    b = float(bundled[bundled.Time == 2020].CBR.iloc[0])
    assert np.isclose(a, b) # Same number, from a different route: the bundled build and the bulk CSV agree

    df = ssd.fetch("kenya", which="births", years=2020, verbose=False)
    prov = df.attrs["provenance"]
    assert prov.license == "CC BY 3.0 IGO" # WPP's license
    assert prov.variant == "Medium" # The default variant
    assert prov.tier == 1 # Fetched
    assert prov.files[0]["sha256"] # The cached file is fingerprinted
    assert df.attrs["location"] == "Kenya" # Canonical location

    info = ssd.cache_info()
    wpp = info[info.file.str.startswith("wpp/")] # The cache is shared with the boundary sources
    assert any("Demographic_Indicators" in name for name in wpp.file) # The download is cached
    assert all(wpp.url.str.startswith("https://population.un.org")) # And recorded with its URL
    return fetched


@pytest.mark.network
@sc.timer()
def test_fetch_variant():
    """ A high-fertility projection has more births than the medium one """
    sc.heading("Testing fetching variants")
    high = ssd.fetch("kenya", which="births", years=2050, variant="High", verbose=False)
    medium = ssd.fetch("kenya", which="births", years=2050, variant="Medium", verbose=False)
    assert float(high.CBR.iloc[0]) > float(medium.CBR.iloc[0]) # The variants differ, in the right direction
    return high


@pytest.mark.network
@sc.timer()
def test_fetch_migration():
    """ Migration has the bundled schema """
    sc.heading("Testing fetching migration")
    df = ssd.fetch("KEN", which="migration", years=(2020, 2022), verbose=False)
    assert list(df.columns) == ["Time", "CNMR"] # The bundled schema
    assert len(df) == 3 # One row per year
    return df


@pytest.mark.network
@sc.timer()
def test_fetch_population():
    """ Upstream is in thousands; load() returns persons, so fetch() must too """
    sc.heading("Testing fetching population")
    fetched = ssd.fetch("kenya", which="population", years=2020, verbose=False)
    bundled = ssd.load("Kenya", which="population")
    bundled = bundled[bundled.Time == 2020]
    assert list(fetched.columns) == ["Time", "Sex", "AgeGrp", "Value"] # The bundled schema
    merged = fetched.merge(bundled, on=["Time", "Sex", "AgeGrp"], suffixes=("_f", "_b"))
    assert len(merged) == len(bundled) # Every bundled row has a match
    assert (merged.Value_f - merged.Value_b).abs().max() <= 0.5 # The bulk CSV is rounded to whole persons, so half a person is the worst case
    return merged


@pytest.mark.network
@sc.timer()
def test_fetch_indicators():
    """ The indicators file is the point: CDR, TFR, LEx and IMR are not bundled anywhere """
    sc.heading("Testing fetching indicators")
    df = ssd.fetch("kenya", which="indicators", years=(2020, 2021), verbose=False)
    for col in ("CBR", "CDR", "TFR", "LEx", "IMR"):
        assert col in df.columns, f"Expected a {col} column"
    assert "ISO3_code" not in df.columns # Metadata columns dropped
    assert len(df) == 2 # One row per year
    return df


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_fetch_deaths():
    """ The fetched death rates match the bundled ones """
    sc.heading("Testing fetching deaths")
    fetched = ssd.fetch("kenya", which="deaths", years=(2019, 2021), verbose=False)
    bundled = ssd.load("Kenya", which="deaths")
    assert list(fetched.columns) == ["Time", "Sex", "AgeGrpStart", "mx"] # The bundled schema
    assert set(fetched.Sex) == {"Female", "Male"} # "Total" dropped, as in load()
    bundled = bundled[bundled.Time == 2020]
    merged = fetched[fetched.Time == 2020].merge(bundled, on=["Time", "Sex", "AgeGrpStart"], suffixes=("_f", "_b"))
    assert len(merged) == len(bundled) # Every bundled row has a match
    assert np.allclose(merged.mx_f, merged.mx_b, rtol=1e-4) # And the same rate
    return merged


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_fetch_life_table():
    """ The life table has every column in the glossary, and a survivorship curve that falls """
    sc.heading("Testing fetching the life table")
    df = ssd.fetch("KEN", which="life_table", years=2020, verbose=False)
    for col in ssd.fetching.LIFE_TABLE_GLOSSARY:
        assert col in df.columns, f"Expected a {col} column"
    assert set(df.Sex) == {"Female", "Male", "Total"} # Unlike deaths, all sexes kept
    assert set(df.attrs["columns"]) == set(ssd.fetching.LIFE_TABLE_GLOSSARY) # The glossary travels with the frame
    female = df[df.Sex == "Female"].sort_values("AgeGrpStart")
    assert female.lx.iloc[0] == pytest.approx(100000) # lx is a survivorship curve out of 100,000 births
    assert (female.lx.diff().dropna() <= 0).all() # Monotonically decreasing
    return df


if __name__ == "__main__":
    do_network = False # Set to True to also run the tests that download (~145 MB of it for the life tables)
    import conftest
    conftest.isolate_cache() # pytest does this through conftest.py; a script has to ask

    T = sc.timer()

    fetchable = test_fetchable()
    years     = test_parse_years()
    files     = test_files()
    if do_network:
        births     = test_fetch_births()
        variant    = test_fetch_variant()
        migration  = test_fetch_migration()
        population = test_fetch_population()
        indicators = test_fetch_indicators()
        deaths     = test_fetch_deaths()
        life_table = test_fetch_life_table()

    T.toc()
