"""Tests for dataset provenance and revision handling."""

import pytest

import starsim_data as ssd

# Every bundled dataset must be attributable: these are third-party data under their
# own licenses, so a store without a source and license is a compliance problem, not
# just a missing nicety.
REQUIRED = ("dataset", "source", "source_url", "license", "citation", "built", "builder")


@pytest.mark.parametrize("which", ssd.list_datasets())
def test_every_dataset_has_provenance(which):
    prov = ssd.provenance(which)
    for field in REQUIRED:
        assert prov.get(field), f"{which!r} provenance is missing {field!r}"


@pytest.mark.parametrize("which, license", [
    ("prem2017", "GPL-3.0"),
    ("prem2021", "GPL-3.0"),
    ("mistry2021", "Apache-2.0"),
    ("deaths", "CC BY 3.0 IGO"),
])
def test_licenses_match_notice(which, license):
    """Licenses recorded in the data must match the ones asserted in NOTICE.md.

    If these drift apart, the machine-readable attribution and the human-readable
    attribution disagree, and one of them is wrong.
    """
    assert ssd.provenance(which).license == license


def test_provenance_with_no_argument_covers_all_datasets():
    allprov = ssd.provenance()
    assert set(allprov.keys()) == set(ssd.list_datasets())


def test_provenance_records_the_build():
    prov = ssd.provenance("prem2017")
    assert prov.builder.endswith("build_hdf5.py")
    assert prov.built.startswith("20")          # ISO timestamp
    assert prov.package_version


def test_loaded_frames_carry_provenance():
    df = ssd.load("Kenya", which="prem2017")
    assert df.attrs["provenance"].license == "GPL-3.0"
    assert df.attrs["location"] == "Kenya"
    assert df.attrs["dataset"] == "prem2017"


def test_provenance_survives_an_alias_lookup():
    df = ssd.load("KEN", which="deaths")
    assert df.attrs["location"] == "Kenya"      # canonical, not the alias


def test_list_revisions():
    revisions = ssd.list_revisions()
    assert revisions == sorted(revisions)
    assert "2024" in revisions


def test_default_revision_is_the_newest():
    newest = ssd.list_revisions()[-1]
    default = ssd.load("Kenya", which="deaths")
    pinned = ssd.load("Kenya", which="deaths", revision=newest)
    assert default.equals(pinned)


def test_revision_can_be_int_or_str():
    a = ssd.load("Kenya", which="deaths", revision=2024)
    b = ssd.load("Kenya", which="deaths", revision="2024")
    assert a.equals(b)


def test_unknown_revision_raises():
    with pytest.raises(ValueError, match="unknown revision"):
        ssd.load("Kenya", which="deaths", revision=1999)


def test_revision_is_rejected_for_contact_matrices():
    """Contact sources are versioned by name, so a revision argument is a mistake."""
    with pytest.raises(ValueError, match="does not apply"):
        ssd.load("Kenya", which="prem2017", revision=2024)


@pytest.mark.xfail(reason="Namibia was omitted from the WPP download by the ISO-2 'NA' "
                          "NaN bug; the code is fixed but the data needs re-downloading "
                          "with a WPP API token (see raw_data/demographics/README.md)",
                   strict=True)
def test_namibia_has_demographic_data():
    """Namibia should be present in the demographic series like any other country.

    Expected to fail until `scripts/download_wpp.py` is re-run: the bug that dropped
    it is fixed, but the raw CSVs in the repo predate the fix. Flips to passing (and
    this marker should then be removed) once the data is refetched.
    """
    assert "Namibia" in ssd.list_locations("deaths")
