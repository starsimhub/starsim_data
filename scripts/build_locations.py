"""
Fill the derived columns of `starsim_data/data/locations.csv`.

Dev/CI tool -- NOT part of the installed package. `locations.csv` is the canonical
location table: which locations exist, their ISO-2 code, and which contact sources
cover them. Those columns are hand-maintained. This script fills the three *derived*
columns used for name resolution at runtime, joining on the hand-maintained ISO-2
code:

- `iso3`           -- ISO 3166-1 alpha-3 code.
- `official_name`  -- the long-form name (e.g. "Republic of Kenya").
- `aliases`        -- pipe-separated alternative names that should resolve to this
                      location: the ISO short name, the common name, translations,
                      and a curated set of abbreviations that no amount of fuzzy
                      matching will reach (`USA`, `UK`, `DRC`, ...).

Everything is derived from `pycountry` (which bundles the ISO 3166 tables and their
translations), so `pycountry` is a *build-time* dependency only -- the resolver in
`starsim_data/locations.py` reads the generated CSV and needs nothing extra.

Aliases that would resolve to more than one location are dropped, with a warning:
an ambiguous alias is worse than no alias, since it would silently pick a country.

Usage:

```bash
python scripts/build_locations.py            # rewrite locations.csv in place
python scripts/build_locations.py --check    # report what would change, write nothing
```
"""

import argparse
import gettext
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pycountry

REPO = Path(__file__).resolve().parent.parent
LOCATIONS_CSV = REPO / "starsim_data" / "data" / "locations.csv"

# Columns this script owns. Everything else in the file is hand-maintained.
DERIVED = ["iso3", "official_name", "aliases"]

# Column order of the rewritten file: hand-maintained identity first, then derived
# name-resolution columns, then the hand-maintained source metadata.
COLUMN_ORDER = ["location", "level", "iso_code", "iso3", "official_name", "aliases",
                "primary_contact_source", "contact_sources", "population_source"]

# Translations to include as aliases. French follows the precedent set by laser-init
# (whose French name table motivated this); Spanish and Portuguese cover the rest of
# the languages common in the regions these data get used for.
LANGUAGES = ["fr", "es", "pt"]

# Abbreviations and informal names, keyed by ISO-2. These are below any sensible
# edit-distance threshold, so they cannot be recovered by fuzzy matching (`sc.suggest`
# returns None for "USA") and have to be listed explicitly.
EXTRA_ALIASES = {
    "AE": ["UAE"],
    "CD": ["DRC", "DR Congo", "Congo-Kinshasa", "Congo DR", "Zaire"],
    "CG": ["Congo-Brazzaville", "Republic of the Congo"],
    "CI": ["Ivory Coast"],
    "CZ": ["Czech Republic"],
    "GB": ["UK", "Britain", "Great Britain"],
    "KP": ["DPRK", "North Korea"],
    "KR": ["ROK", "South Korea"],
    "LA": ["Laos"],
    "MM": ["Burma"],
    "NL": ["Holland"],
    "RU": ["Russia"],
    "SY": ["Syria"],
    "TR": ["Turkey"],
    "TW": ["Taiwan"],
    "TZ": ["Tanzania"],
    "US": ["USA", "US", "America"],
    "VA": ["Vatican", "Vatican City"],
    "VE": ["Venezuela"],
    "VN": ["Vietnam", "Viet Nam"],
}


def normalize(name):
    """Collapse a location string to its match key.

    Mirrors `starsim_data.locations.normalize` exactly -- the two must agree, since
    this script decides which aliases are distinct and the resolver decides which
    ones match. Kept duplicated rather than imported so the build script does not
    depend on the package being importable.
    """
    decomposed = unicodedata.normalize("NFKD", str(name or "").strip())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = "".join(" " if c in "-_/" else c for c in stripped.casefold()
                      if c.isalnum() or c in " -_/")
    return "_".join(cleaned.split())


def fields(country):
    """Return a pycountry record's fields as a plain dict.

    `common_name` and `official_name` are present on some records and absent on
    others, so the optionality is real rather than a type question. Collapsing the
    record to a dict once, here, keeps that in a single place and lets everything
    downstream use plain key access.
    """
    keys = ("alpha_2", "alpha_3", "name", "common_name", "official_name")
    return {key: getattr(country, key, None) for key in keys}


def translators():
    """Return one gettext translator per language in LANGUAGES (skipping any missing)."""
    out = {}
    for lang in LANGUAGES:
        try:
            out[lang] = gettext.translation("iso3166-1", pycountry.LOCALES_DIR,
                                            languages=[lang])
        except FileNotFoundError:
            print(f"  note: no {lang!r} translations in pycountry, skipping")
    return out


def candidate_aliases(country, trans):
    """Collect every alternative name for one country, in priority order."""
    names = [country["name"], country["common_name"]]
    names += EXTRA_ALIASES.get(country["alpha_2"], [])
    names += [t.gettext(country["name"]) for t in trans.values()]
    return [name for name in names if name]


def read_locations(path=LOCATIONS_CSV):
    """Read locations.csv without pandas' NA coercion.

    Namibia's ISO-2 code is the string "NA", which pandas' default `na_values` turns
    into NaN -- silently dropping Namibia from anything keyed on ISO-2. Every reader
    of this file must disable that, so it is done in one place.
    """
    return pd.read_csv(path, keep_default_na=False, na_values=[])


def build(check=False):
    df = read_locations()
    trans = translators()
    print(f"Read {len(df)} locations from {LOCATIONS_CSV.name}; "
          f"translations: {', '.join(trans) or 'none'}")

    # Pass 1: gather candidate aliases per location, and index them by match key so
    # collisions across locations can be found before anything is written.
    proposed = {}
    by_key = defaultdict(set)
    unmatched = []

    for row in df.itertuples():
        record = pycountry.countries.get(alpha_2=str(row.iso_code).upper())
        if record is None:
            unmatched.append(f"{row.location} ({row.iso_code})")
            proposed[row.location] = (None, None, [])
            continue
        country = fields(record)
        official = country["official_name"] or country["name"]
        aliases = candidate_aliases(country, trans)
        proposed[row.location] = (country["alpha_3"], official, aliases)
        # The canonical name, ISO codes and official name are matched by the resolver
        # from their own columns; index them here only to detect collisions.
        for name in [row.location, country["alpha_2"], country["alpha_3"], official, *aliases]:
            by_key[normalize(name)].add(row.location)

    if unmatched:
        print(f"  WARNING: {len(unmatched)} location(s) not found in pycountry by ISO-2: "
              f"{', '.join(unmatched)}")

    # Pass 2: drop any alias that is ambiguous across locations.
    ambiguous = {k: sorted(v) for k, v in by_key.items() if len(v) > 1}
    for key, locations in ambiguous.items():
        print(f"  WARNING: alias {key!r} is ambiguous ({', '.join(locations)}); dropping it")

    rows = []
    for row in df.itertuples():
        iso3, official, aliases = proposed[row.location]
        # Deduplicate by match key, drop ambiguous ones, and drop anything the
        # resolver already covers from a dedicated column.
        covered = {normalize(n) for n in (row.location, row.iso_code, iso3, official) if n}
        kept, seen = [], set()
        for alias in aliases:
            key = normalize(alias)
            if key in covered or key in seen or key in ambiguous:
                continue
            seen.add(key)
            kept.append(alias)
        rows.append({"iso3": iso3 or "", "official_name": official or "",
                     "aliases": "|".join(kept)})

    derived = pd.DataFrame(rows, index=df.index)
    out = df.drop(columns=[c for c in DERIVED if c in df.columns]).join(derived)
    out = out[[c for c in COLUMN_ORDER if c in out.columns]]

    n_aliases = sum(len(r["aliases"].split("|")) if r["aliases"] else 0 for r in rows)
    missing_iso3 = sum(1 for r in rows if not r["iso3"])
    print(f"  {n_aliases} aliases across {len(rows)} locations "
          f"({n_aliases/len(rows):.1f} each); {missing_iso3} without an ISO-3 code")

    if check:
        before = read_locations()
        same = before.columns.equals(out.columns) and before.equals(out)
        print("No changes." if same else "Would change locations.csv (run without --check).")
        return

    out.to_csv(LOCATIONS_CSV, index=False)
    print(f"  wrote {LOCATIONS_CSV}")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()
    build(check=args.check)


if __name__ == "__main__":
    main()
