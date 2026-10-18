"""
Test location name resolution and administrative-level parsing
"""

import sciris as sc
import pytest

import starsim_data as ssd


@sc.timer()
def test_canonical():
    """ Every canonical name, and every key in every bundled store, resolves to itself """
    sc.heading("Testing canonical names")
    for location in ssd.list_all_locations():
        assert ssd.resolve(location) == location, f"Expected {location!r} to resolve to itself"

    # If this fails, a dataset has a location that locations.csv does not know about, so
    # its metadata (ISO codes, aliases) is silently missing.
    for which in ssd.list_datasets(tier=0):
        for location in ssd.list_locations(which):
            assert ssd.resolve(location) == location, f"{location!r} in {which!r}"


@sc.timer()
def test_resolve():
    """ Names, codes and aliases resolve to the canonical name """
    sc.heading("Testing aliases")
    aliases = {
        "Kenya":                    "Kenya",
        "kenya":                    "Kenya",
        " KENYA ":                  "Kenya",
        "KE":                       "Kenya", # ISO-2
        "KEN":                      "Kenya", # ISO-3
        "Republic of Kenya":        "Kenya", # Official name
        "USA":                      "United_States", # Abbreviation: below any fuzzy threshold
        "US":                       "United_States",
        "united states":            "United_States",
        "United States of America": "United_States",
        "America":                  "United_States",
        "UK":                       "United_Kingdom",
        "Britain":                  "United_Kingdom",
        "DRC":                      "Democratic_Republic_of_the_Congo",
        "Zaire":                    "Democratic_Republic_of_the_Congo",
        "Ivory Coast":              "Cote_dIvoire",
        "Côte d'Ivoire":            "Cote_dIvoire", # Accents and punctuation
        "cote divoire":             "Cote_dIvoire",
        "Viet Nam":                 "Vietnam",
        "Allemagne":                "Germany", # French, from pycountry's translations
        "Chine":                    "China",
        "Alemania":                 "Germany", # Spanish
    }
    for query, expected in aliases.items():
        assert ssd.resolve(query) == expected, f"Expected {query!r} to resolve to {expected!r}"
    return aliases


@sc.timer()
def test_namibia():
    """
    Namibia's ISO-2 code is the string 'NA'.

    Read with pandas' defaults it becomes NaN, which silently dropped Namibia from every
    ISO-2-keyed lookup. If this fails, some reader of locations.csv has reintroduced the
    default NA coercion.
    """
    sc.heading("Testing Namibia's ISO-2 code")
    info = ssd.location_info("Namibia")
    assert ssd.resolve("NA") == "Namibia" # "NA" is a code, not a missing value
    assert info.iso_code == "NA" # Stored as the string
    assert info.iso3 == "NAM" # And the rest of the row is intact
    return info


@sc.timer()
def test_unknown():
    """ Resolution is exact: fuzzy matching only ever suggests """
    sc.heading("Testing unknown locations")
    with pytest.raises(KeyError, match="did you mean"): # A transposition gets suggestions...
        ssd.resolve("Keyna")
    with pytest.raises(KeyError, match="Kenya"): # ...naming the right country
        ssd.resolve("Keyna")
    with pytest.raises(KeyError): # Nonsense may get candidates, but is never resolved
        ssd.resolve("Atlantis")
    with pytest.raises(KeyError): # A near-miss raises rather than resolving to the nearest name
        ssd.resolve("Kenyaa")


@sc.timer()
def test_valid():
    """ `valid` scopes resolution to the locations a dataset has """
    sc.heading("Testing scoped resolution")
    # Kenya is in prem2017 but not in mistry2021's smaller country set
    assert ssd.resolve("KEN", valid=ssd.list_locations("prem2017")) == "Kenya" # In scope
    with pytest.raises(KeyError): # Out of scope
        ssd.resolve("KEN", valid=ssd.list_locations("mistry2021"))


@sc.timer()
def test_location_info():
    """ location_info() gives the codes, level and sources, for any alias """
    sc.heading("Testing location_info")
    info = ssd.location_info("USA")
    assert info.location == "United_States" # Canonical name
    assert info.iso_code == "US" # ISO-2
    assert info.iso3 == "USA" # ISO-3
    assert info.level == 0 # A country
    assert "mistry2021" in info.contact_sources # Which contact sources have it
    assert ssd.location_info("KEN").location == ssd.location_info("kenya").location # Any alias works
    return info


@sc.timer()
def test_parse_level():
    """ Administrative levels parse from the usual spellings, and nothing else """
    sc.heading("Testing parse_level")
    levels = {"admin0": 0, "admin1": 1, "ADM2": 2, "adm3": 3, "4": 4, "level2": 2, 0: 0, 2: 2}
    for raw, expected in levels.items():
        assert ssd.parse_level(raw) == expected, f"Expected {raw!r} to parse to {expected}"
    for bad in ["admin9", "6", -1, "banana", "", None, True]:
        with pytest.raises(ValueError):
            ssd.parse_level(bad)
    return levels


@sc.timer()
def test_normalize():
    """ normalize() collapses equivalent spellings, and tolerates non-strings """
    sc.heading("Testing normalize")
    pairs = [
        ("Côte d'Ivoire", "Cote_dIvoire"),
        ("united states", "United_States"),
        ("  KENYA  ", "kenya"),
        ("Timor-Leste", "Timor_Leste"),
    ]
    for a, b in pairs:
        assert ssd.locations.normalize(a) == ssd.locations.normalize(b), f"Expected {a!r} and {b!r} to normalize the same"
    assert ssd.locations.normalize(None) == "" # Not a crash
    assert ssd.locations.normalize(float("nan")) == "nan" # Not a crash either; simply matches nothing
    return pairs


if __name__ == "__main__":
    T = sc.timer()

    test_canonical()
    aliases   = test_resolve()
    namibia   = test_namibia()
    test_unknown()
    test_valid()
    info      = test_location_info()
    levels    = test_parse_level()
    pairs     = test_normalize()

    T.toc()
