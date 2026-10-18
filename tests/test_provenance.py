"""
Test dataset provenance and revision handling
"""

import sciris as sc
import pytest

import starsim_data as ssd

# Every bundled dataset must be attributable: these are third-party data under their
# own licenses, so a store without a source and license is a compliance problem, not
# just a missing nicety.
REQUIRED = ("dataset", "source", "source_url", "license", "citation", "built", "builder")


@sc.timer()
def test_provenance():
    """ Every bundled dataset records where it came from and how it was built """
    sc.heading("Testing provenance")
    for which in ssd.list_datasets(tier=0):
        prov = ssd.provenance(which)
        for field in REQUIRED:
            assert prov.get(field), f"{which!r} provenance is missing {field!r}"

    allprov = ssd.provenance()
    assert set(allprov.keys()) == set(ssd.list_datasets(tier=0)) # No argument covers every bundled dataset

    prov = ssd.provenance("prem2017")
    assert prov.builder.endswith("build_hdf5.py") # The script that built it
    assert prov.built.startswith("20") # An ISO timestamp
    assert prov.package_version # The version that built it
    return allprov


@sc.timer()
def test_licenses():
    """
    Licenses recorded in the data must match the ones asserted in NOTICE.md.

    If these drift apart, the machine-readable attribution and the human-readable
    attribution disagree, and one of them is wrong.
    """
    sc.heading("Testing licenses")
    licenses = {
        "prem2017":   "GPL-3.0",
        "prem2021":   "GPL-3.0",
        "mistry2021": "Apache-2.0",
        "deaths":     "CC BY 3.0 IGO",
    }
    for which, license in licenses.items():
        assert ssd.provenance(which).license == license, f"Expected {which} to be {license}, as NOTICE.md says"
    return licenses


@sc.timer()
def test_attrs():
    """ Loaded frames carry their provenance, location and dataset """
    sc.heading("Testing provenance on loaded frames")
    df = ssd.load("Kenya", which="prem2021")
    assert df.attrs["provenance"].license == "GPL-3.0" # The provenance travels with the data
    assert df.attrs["location"] == "Kenya" # So does the location
    assert df.attrs["dataset"] == "prem2021" # And the dataset
    assert ssd.load("KEN", which="deaths").attrs["location"] == "Kenya" # Canonical, not the alias
    return df


@sc.timer()
def test_revisions():
    """ WPP revisions: listed, defaulting to the newest, and refused where they mean nothing """
    sc.heading("Testing revisions")
    revisions = ssd.list_revisions()
    assert revisions == sorted(revisions) # Sorted
    assert "2024" in revisions # The current WPP

    default = ssd.load("Kenya", which="deaths")
    assert default.equals(ssd.load("Kenya", which="deaths", revision=revisions[-1])) # The default is the newest
    assert ssd.load("Kenya", which="deaths", revision=2024).equals(ssd.load("Kenya", which="deaths", revision="2024")) # An int or a str

    with pytest.raises(ValueError, match="unknown revision"):
        ssd.load("Kenya", which="deaths", revision=1999)
    with pytest.raises(ValueError, match="does not apply"): # Contact sources are versioned by name, so a revision is a mistake
        ssd.load("Kenya", which="prem2021", revision=2024)
    return revisions


@sc.timer()
def test_namibia():
    """
    Namibia is present in every demographic series, like any other country.

    A regression test for the ISO-2 `NA` bug: pandas' default `na_values` read Namibia's
    country code as NaN, which dropped it from the WPP download and from every
    ISO-2-keyed lookup downstream.
    """
    sc.heading("Testing Namibia's demographic data")
    for which in ["births", "deaths", "migration", "population"]:
        assert "Namibia" in ssd.list_locations(which), f"Expected Namibia in {which}"


if __name__ == "__main__":
    T = sc.timer()

    prov      = test_provenance()
    licenses  = test_licenses()
    df        = test_attrs()
    revisions = test_revisions()
    test_namibia()

    T.toc()
