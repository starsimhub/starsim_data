"""Tests for `fetch()`.

The tests that actually download are marked `network` and are deselected by default in
CI; everything below the divider runs offline. Set `STARSIM_DATA_CACHE_DIR` to reuse the
downloads between runs -- the life-table half alone is ~145 MB.
"""

import numpy as np
import pytest

import starsim_data as ssd

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --- Offline ----------------------------------------------------------------------- #

def test_list_fetchable_covers_the_bundled_series():
    fetchable = ssd.list_fetchable()
    for name in ("births", "deaths", "migration", "population"):
        assert name in fetchable
    assert "life_table" in fetchable and "indicators" in fetchable


def test_unknown_series_suggests_alternatives():
    with pytest.raises(ValueError, match="did you mean.*births"):
        ssd.fetch("Kenya", which="birth")


@pytest.mark.parametrize("years, expected", [
    (None, None),
    (2020, [2020]),
    ((2000, 2003), [2000, 2001, 2002, 2003]),          # a 2-tuple is an inclusive range
    ([2000, 2020, 2010], [2000, 2010, 2020]),          # a list is exactly those years
    (range(2000, 2003), [2000, 2001, 2002]),
])
def test_parse_years(years, expected):
    assert ssd.fetching._parse_years(years) == expected


def test_parse_years_rejects_a_backwards_range():
    with pytest.raises(ValueError, match="inclusive"):
        ssd.fetching._parse_years((2020, 2000))


def test_parse_years_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        ssd.fetching._parse_years([])


def test_life_tables_are_medium_only():
    """The UN publishes no non-Medium life table, so asking for one must fail clearly."""
    with pytest.raises(ValueError, match="Medium variant only"):
        ssd.fetch("Kenya", which="deaths", variant="High")


@pytest.mark.parametrize("years, n_files", [
    (None, 2),              # both halves
    ([2020], 1),            # estimates only
    ([2030], 1),            # projections only
    ([2020, 2030], 2),      # spans the split
])
def test_split_files_are_selected_by_year(years, n_files):
    """Only the halves of the life table that cover the requested years get downloaded."""
    urls = ssd.fetching.FILES["life_table"].urls("2024", "Medium", years)
    assert len(urls) == n_files


def test_variant_selects_the_other_variants_file():
    medium = ssd.fetching.FILES["indicators"].urls("2024", "Medium", None)
    other = ssd.fetching.FILES["indicators"].urls("2024", "High", None)
    assert "Medium" in list(medium)[0]
    assert "OtherVariants" in list(other)[0]


def test_unknown_revision_split_is_reported():
    with pytest.raises(ValueError, match="year split"):
        ssd.fetching.FILES["life_table"].urls("2099", "Medium", None)


def test_fetch_only_datasets_are_in_the_registry_as_tier_2():
    for name in ("life_table", "indicators"):
        assert ssd.registry.dataset(name).tier == 1


# --- Network ------------------------------------------------------------------------ #

@pytest.mark.network
def test_fetch_births_matches_the_bundled_value():
    """Same number, from a different route: the bundled build and the bulk CSV agree."""
    fetched = ssd.fetch("kenya", which="births", years=(2018, 2024), verbose=False)
    bundled = ssd.load("Kenya", which="births")
    assert list(fetched.columns) == ["Time", "CBR"]
    assert fetched.Time.tolist() == list(range(2018, 2025))     # annual, not decadal
    a = float(fetched[fetched.Time == 2020].CBR.iloc[0])
    b = float(bundled[bundled.Time == 2020].CBR.iloc[0])
    assert np.isclose(a, b)


@pytest.mark.network
def test_fetch_carries_provenance():
    df = ssd.fetch("kenya", which="births", years=2020, verbose=False)
    prov = df.attrs["provenance"]
    assert prov.license == "CC BY 3.0 IGO"
    assert prov.variant == "Medium"
    assert prov.tier == 1
    assert prov.files[0]["sha256"]              # the cached file is fingerprinted
    assert df.attrs["location"] == "Kenya"


@pytest.mark.network
def test_fetch_migration_schema():
    df = ssd.fetch("KEN", which="migration", years=(2020, 2022), verbose=False)
    assert list(df.columns) == ["Time", "CNMR"]
    assert len(df) == 3


@pytest.mark.network
def test_fetch_population_is_in_persons():
    """Upstream is in thousands; `load()` returns persons, so `fetch()` must too."""
    fetched = ssd.fetch("kenya", which="population", years=2020, verbose=False)
    bundled = ssd.load("Kenya", which="population")
    bundled = bundled[bundled.Time == 2020]
    assert list(fetched.columns) == ["Time", "Sex", "AgeGrp", "Value"]
    merged = fetched.merge(bundled, on=["Time", "Sex", "AgeGrp"], suffixes=("_f", "_b"))
    assert len(merged) == len(bundled)
    # The bulk CSV is rounded to whole persons, so half a person is the worst case.
    assert (merged.Value_f - merged.Value_b).abs().max() <= 0.5


@pytest.mark.network
def test_fetch_other_variants_differ_from_medium():
    high = ssd.fetch("kenya", which="births", years=2050, variant="High", verbose=False)
    medium = ssd.fetch("kenya", which="births", years=2050, variant="Medium", verbose=False)
    assert float(high.CBR.iloc[0]) > float(medium.CBR.iloc[0])


@pytest.mark.network
def test_fetch_indicators_has_the_extra_columns():
    """The indicators file is the point: CDR, TFR, LEx and IMR are not bundled anywhere."""
    df = ssd.fetch("kenya", which="indicators", years=(2020, 2021), verbose=False)
    for col in ("CBR", "CDR", "TFR", "LEx", "IMR"):
        assert col in df.columns
    assert "ISO3_code" not in df.columns            # metadata columns dropped
    assert len(df) == 2


@pytest.mark.network
@pytest.mark.slow
def test_fetch_deaths_matches_the_bundled_value():
    fetched = ssd.fetch("kenya", which="deaths", years=(2019, 2021), verbose=False)
    bundled = ssd.load("Kenya", which="deaths")
    assert list(fetched.columns) == ["Time", "Sex", "AgeGrpStart", "mx"]
    assert set(fetched.Sex) == {"Female", "Male"}   # "Total" dropped, as in load()
    merged = fetched[fetched.Time == 2020].merge(bundled[bundled.Time == 2020],
                                                 on=["Time", "Sex", "AgeGrpStart"],
                                                 suffixes=("_f", "_b"))
    assert len(merged) == len(bundled[bundled.Time == 2020])
    assert np.allclose(merged.mx_f, merged.mx_b, rtol=1e-4)


@pytest.mark.network
@pytest.mark.slow
def test_fetch_life_table_has_the_full_glossary():
    df = ssd.fetch("KEN", which="life_table", years=2020, verbose=False)
    for col in ssd.fetching.LIFE_TABLE_GLOSSARY:
        assert col in df.columns
    assert set(df.Sex) == {"Female", "Male", "Total"}   # unlike deaths, all sexes kept
    assert set(df.attrs["columns"]) == set(ssd.fetching.LIFE_TABLE_GLOSSARY)
    # lx is a survivorship curve out of 100,000 births: monotonically decreasing.
    female = df[df.Sex == "Female"].sort_values("AgeGrpStart")
    assert female.lx.iloc[0] == pytest.approx(100000)
    assert (female.lx.diff().dropna() <= 0).all()


@pytest.mark.network
def test_fetch_caches_and_records_the_download():
    ssd.fetch("kenya", which="births", years=2020, verbose=False)
    info = ssd.cache_info()
    # Scope to the WPP subdirectory: the cache is shared with the boundary sources.
    wpp = info[info.file.str.startswith("wpp/")]
    assert any("Demographic_Indicators" in name for name in wpp.file)
    assert all(wpp.url.str.startswith("https://population.un.org"))
