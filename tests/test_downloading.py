"""
Test download(), and fetch() passing on to it what is not packaged.

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
def test_downloadable():
    """ The downloadable series are listed and registered as tier 1, and a typo gets suggestions """
    sc.heading("Testing the downloadable series")
    downloadable = ssd.list_downloadable()
    for name in ("births", "deaths", "migration", "population", "fertility", "life_table", "indicators"):
        assert name in downloadable, f"Expected {name} to be downloadable"
    for name in ("life_table", "indicators"):
        assert ssd.registry.dataset(name).tier == 1, f"Expected download-only {name} to be tier 1"
        assert ssd.registry.dataset(name).function == "download", f"Expected {name} to be got with download()"
    assert not set(downloadable) & set(ssd.list_fetchable()) # Each is got one way
    with pytest.raises(ValueError, match="did you mean.*births"):
        ssd.download("Kenya", which="birth")
    with pytest.raises(ValueError, match="published with this package.*use fetch"): # A published store is fetched
        ssd.download("Japan", which="prem2017")
    return downloadable


@sc.timer()
def test_fetch_passes_on():
    """ fetch() of data that is not packaged warns that it is external, then calls download() """
    sc.heading("Testing fetch() of data that is not packaged")
    with pytest.warns(UserWarning, match=r"not packaged.*UN WPP.*download\('Kenya', which='deaths'\)") as record:
        with pytest.raises(ValueError, match="Medium variant only"): # Raised by download(), so the request reached it
            ssd.fetch("Kenya", which="deaths", variant="High")
    assert record[0].filename == __file__ # The warning points at the caller
    return record


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
        assert ssd.downloading._parse_years(years) == expected, f"Expected {years!r} to parse to {expected}"
    with pytest.raises(ValueError, match="inclusive"): # A backwards range
        ssd.downloading._parse_years((2020, 2000))
    with pytest.raises(ValueError, match="empty"):
        ssd.downloading._parse_years([])
    return cases


@sc.timer()
def test_files():
    """ Only the files that cover the requested years and variant get downloaded """
    sc.heading("Testing file selection")
    life_table = ssd.downloading.FILES["life_table"]
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

    medium = ssd.downloading.FILES["indicators"].urls("2024", "Medium", None)
    other = ssd.downloading.FILES["indicators"].urls("2024", "High", None)
    assert "Medium" in list(medium)[0] # The Medium variant has its own file
    assert "OtherVariants" in list(other)[0] # The rest share one
    fertility = ssd.downloading.FILES["fertility"]
    assert fertility.urls("2024", "Medium", None) == fertility.urls("2024", "High", None) # Every variant is in one file

    with pytest.raises(ValueError, match="Medium variant only"): # The UN publishes no non-Medium life table
        ssd.download("Kenya", which="deaths", variant="High")
    return cases


# %% Network

@pytest.mark.network
@sc.timer()
def test_download_births():
    """ The downloaded births match the bundled ones, carry provenance and are cached """
    sc.heading("Testing downloading births")
    downloaded = ssd.download("kenya", which="births", years=(2018, 2024), verbose=False)
    bundled = ssd.load("Kenya", which="births")
    assert list(downloaded.columns) == ["Time", "CBR"] # The bundled schema
    assert downloaded.Time.tolist() == list(range(2018, 2025)) # Annual, not decadal
    a = float(downloaded[downloaded.Time == 2020].CBR.iloc[0])
    b = float(bundled[bundled.Time == 2020].CBR.iloc[0])
    assert np.isclose(a, b) # Same number, from a different route: the bundled build and the bulk CSV agree

    df = ssd.download("kenya", which="births", years=2020, verbose=False)
    prov = df.attrs["provenance"]
    assert prov.license == "CC BY 3.0 IGO" # WPP's license
    assert prov.variant == "Medium" # The default variant
    assert prov.tier == 1 # Not bundled
    assert prov.files[0]["sha256"] # The cached file is fingerprinted
    assert df.attrs["location"] == "Kenya" # Canonical location

    info = ssd.cache_info()
    wpp = info[info.file.str.startswith("wpp/")] # The cache is shared with the boundary sources
    assert any("Demographic_Indicators" in name for name in wpp.file) # The download is cached
    assert all(wpp.url.str.startswith("https://population.un.org")) # And recorded with its URL
    return downloaded


@pytest.mark.network
@sc.timer()
def test_download_variant():
    """ A high-fertility projection has more births than the medium one """
    sc.heading("Testing downloading variants")
    high = ssd.download("kenya", which="births", years=2050, variant="High", verbose=False)
    medium = ssd.download("kenya", which="births", years=2050, variant="Medium", verbose=False)
    assert float(high.CBR.iloc[0]) > float(medium.CBR.iloc[0]) # The variants differ, in the right direction
    return high


@pytest.mark.network
@sc.timer()
def test_download_migration():
    """ Migration has the bundled schema """
    sc.heading("Testing downloading migration")
    df = ssd.download("KEN", which="migration", years=(2020, 2022), verbose=False)
    assert list(df.columns) == ["Time", "CNMR"] # The bundled schema
    assert len(df) == 3 # One row per year
    return df


@pytest.mark.network
@sc.timer()
def test_download_population():
    """ Upstream is in thousands; load() returns persons, so download() must too """
    sc.heading("Testing downloading population")
    downloaded = ssd.download("kenya", which="population", years=2020, verbose=False)
    bundled = ssd.load("Kenya", which="population")
    bundled = bundled[bundled.Time == 2020]
    assert list(downloaded.columns) == ["Time", "Sex", "AgeGrp", "Value"] # The bundled schema
    merged = downloaded.merge(bundled, on=["Time", "Sex", "AgeGrp"], suffixes=("_f", "_b"))
    assert len(merged) == len(bundled) # Every bundled row has a match
    assert (merged.Value_f - merged.Value_b).abs().max() <= 0.5 # The bulk CSV is rounded to whole persons, so half a person is the worst case
    return merged


@pytest.mark.network
@sc.timer()
def test_download_fertility():
    """ The downloaded age-specific fertility rates match the bundled ones """
    sc.heading("Testing downloading fertility")
    downloaded = ssd.download("nigeria", which="fertility", years=2020, verbose=False)
    bundled = ssd.load("Nigeria", which="fertility")
    bundled = bundled[bundled.Time == 2020]
    assert list(downloaded.columns) == ["Time", "AgeGrpStart", "ASFR"] # The bundled schema
    merged = downloaded.merge(bundled, on=["Time", "AgeGrpStart"], suffixes=("_f", "_b"))
    assert len(merged) == len(bundled) # Every bundled row has a match
    assert np.allclose(merged.ASFR_f, merged.ASFR_b) # The same values
    return merged


@pytest.mark.network
@sc.timer()
def test_download_indicators():
    """ The indicators file is the point: CDR, TFR, LEx and IMR are not bundled anywhere """
    sc.heading("Testing downloading indicators")
    df = ssd.download("kenya", which="indicators", years=(2020, 2021), verbose=False)
    for col in ("CBR", "CDR", "TFR", "LEx", "IMR"):
        assert col in df.columns, f"Expected a {col} column"
    assert "ISO3_code" not in df.columns # Metadata columns dropped
    assert len(df) == 2 # One row per year
    return df


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_download_deaths():
    """ The downloaded death rates match the bundled ones """
    sc.heading("Testing downloading deaths")
    downloaded = ssd.download("kenya", which="deaths", years=(2019, 2021), verbose=False)
    bundled = ssd.load("Kenya", which="deaths")
    assert list(downloaded.columns) == ["Time", "Sex", "AgeGrpStart", "mx"] # The bundled schema
    assert set(downloaded.Sex) == {"Female", "Male"} # "Total" dropped, as in load()
    bundled = bundled[bundled.Time == 2020]
    merged = downloaded[downloaded.Time == 2020].merge(bundled, on=["Time", "Sex", "AgeGrpStart"], suffixes=("_f", "_b"))
    assert len(merged) == len(bundled) # Every bundled row has a match
    assert np.allclose(merged.mx_f, merged.mx_b, rtol=1e-4) # And the same rate
    return merged


@pytest.mark.network
@pytest.mark.slow
@sc.timer()
def test_download_life_table():
    """ The life table has every column in the glossary, and a survivorship curve that falls """
    sc.heading("Testing downloading the life table")
    df = ssd.download("KEN", which="life_table", years=2020, verbose=False)
    for col in ssd.downloading.LIFE_TABLE_GLOSSARY:
        assert col in df.columns, f"Expected a {col} column"
    assert set(df.Sex) == {"Female", "Male", "Total"} # Unlike deaths, all sexes kept
    assert set(df.attrs["columns"]) == set(ssd.downloading.LIFE_TABLE_GLOSSARY) # The glossary travels with the frame
    female = df[df.Sex == "Female"].sort_values("AgeGrpStart")
    assert female.lx.iloc[0] == pytest.approx(100000) # lx is a survivorship curve out of 100,000 births
    assert (female.lx.diff().dropna() <= 0).all() # Monotonically decreasing
    return df


if __name__ == "__main__":
    do_network = False # Set to True to also run the tests that download (~145 MB of it for the life tables)
    import conftest
    conftest.isolate_cache() # pytest does this through conftest.py; a script has to ask

    T = sc.timer()

    downloadable = test_downloadable()
    passes_on    = test_fetch_passes_on()
    years        = test_parse_years()
    files        = test_files()
    if do_network:
        births     = test_download_births()
        variant    = test_download_variant()
        migration  = test_download_migration()
        population = test_download_population()
        fertility  = test_download_fertility()
        indicators = test_download_indicators()
        deaths     = test_download_deaths()
        life_table = test_download_life_table()

    T.toc()
