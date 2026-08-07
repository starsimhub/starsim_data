"""Tests for location name resolution and administrative-level parsing."""

import pytest

import starsim_data as ssd
from starsim_data.locations import normalize


def test_canonical_names_resolve_to_themselves():
    for location in ssd.list_all_locations():
        assert ssd.resolve(location) == location


def test_location_table_covers_every_dataset_key():
    """Every key in every bundled store must be resolvable.

    If this fails, a dataset has a location that locations.csv does not know about,
    so its metadata (ISO codes, aliases) is silently missing.
    """
    for which in ssd.list_datasets():
        for location in ssd.list_locations(which):
            assert ssd.resolve(location) == location, f"{location!r} in {which!r}"


@pytest.mark.parametrize("query, expected", [
    ("Kenya", "Kenya"),
    ("kenya", "Kenya"),
    (" KENYA ", "Kenya"),
    ("KE", "Kenya"),                    # ISO-2
    ("KEN", "Kenya"),                   # ISO-3
    ("Republic of Kenya", "Kenya"),     # official name
    ("USA", "United_States"),           # abbreviation: below any fuzzy threshold
    ("US", "United_States"),
    ("united states", "United_States"),
    ("United States of America", "United_States"),
    ("America", "United_States"),
    ("UK", "United_Kingdom"),
    ("Britain", "United_Kingdom"),
    ("DRC", "Democratic_Republic_of_the_Congo"),
    ("Zaire", "Democratic_Republic_of_the_Congo"),
    ("Ivory Coast", "Cote_dIvoire"),
    ("Côte d'Ivoire", "Cote_dIvoire"),  # accents and punctuation
    ("cote divoire", "Cote_dIvoire"),
    ("Viet Nam", "Vietnam"),
    ("Allemagne", "Germany"),           # French, from pycountry's translations
    ("Chine", "China"),
    ("Alemania", "Germany"),            # Spanish
])
def test_aliases_resolve(query, expected):
    assert ssd.resolve(query) == expected


def test_namibia_iso2_is_not_swallowed_as_nan():
    """Namibia's ISO-2 code is the string 'NA'.

    Read with pandas' defaults it becomes NaN, which silently dropped Namibia from
    every ISO-2-keyed lookup. If this fails, some reader of locations.csv has
    reintroduced the default NA coercion.
    """
    assert ssd.resolve("NA") == "Namibia"
    assert ssd.location_info("Namibia").iso_code == "NA"
    assert ssd.location_info("Namibia").iso3 == "NAM"


def test_unknown_location_suggests_alternatives():
    with pytest.raises(KeyError, match="did you mean"):
        ssd.resolve("Keyna")            # transposition -> should suggest Kenya


def test_unknown_location_suggestion_names_the_right_country():
    with pytest.raises(KeyError, match="Kenya"):
        ssd.resolve("Keyna")


def test_nonsense_location_still_raises():
    """Fuzzy matching may offer candidates for nonsense, but must never resolve it."""
    with pytest.raises(KeyError):
        ssd.resolve("Atlantis")


def test_resolution_is_exact_not_fuzzy():
    """A near-miss must raise rather than silently resolving to the nearest name."""
    with pytest.raises(KeyError):
        ssd.resolve("Kenyaa")


def test_valid_scopes_resolution_to_a_dataset():
    # Kenya is in prem2017 but not in mistry2021's smaller country set.
    assert ssd.resolve("KEN", valid=ssd.list_locations("prem2017")) == "Kenya"
    with pytest.raises(KeyError):
        ssd.resolve("KEN", valid=ssd.list_locations("mistry2021"))


def test_location_info_fields():
    info = ssd.location_info("USA")
    assert info.location == "United_States"
    assert info.iso_code == "US"
    assert info.iso3 == "USA"
    assert info.level == 0
    assert "mistry2021" in info.contact_sources


def test_location_info_accepts_any_alias():
    assert ssd.location_info("KEN").location == ssd.location_info("kenya").location


@pytest.mark.parametrize("raw, expected", [
    ("admin0", 0), ("admin1", 1), ("ADM2", 2), ("adm3", 3), ("4", 4),
    ("level2", 2), (0, 0), (2, 2),
])
def test_parse_level(raw, expected):
    assert ssd.parse_level(raw) == expected


@pytest.mark.parametrize("bad", ["admin9", "5", -1, "banana", "", None, True])
def test_parse_level_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        ssd.parse_level(bad)


@pytest.mark.parametrize("a, b", [
    ("Côte d'Ivoire", "Cote_dIvoire"),
    ("united states", "United_States"),
    ("  KENYA  ", "kenya"),
    ("Timor-Leste", "Timor_Leste"),
])
def test_normalize_collapses_equivalent_spellings(a, b):
    assert normalize(a) == normalize(b)


def test_normalize_tolerates_non_strings():
    assert normalize(None) == ""
    assert normalize(float("nan")) == "nan"    # not a crash; simply matches nothing
