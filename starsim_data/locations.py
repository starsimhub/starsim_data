"""
Resolve user-supplied location names to canonical dataset keys.

Datasets are keyed by a canonical name (`Kenya`, `United_States`, `Cote_dIvoire`), but
people write locations every other way: ISO codes (`KE`, `USA`), abbreviations (`UK`,
`DRC`), official names, accented spellings, other languages. This module maps all of
them onto the canonical key.

Matching is exact, against a table generated at build time into `data/locations.csv`
(see `scripts/build_locations.py`). Fuzzy matching is used *only* to suggest
alternatives once an exact match has failed -- never to resolve one. That division
matters: fuzzy matching cannot reach abbreviations at all (`sc.suggest('USA', ...)`
returns nothing, the edit distance is too large), and it will cheerfully offer
candidates for input that corresponds to no location whatsoever. It makes a good
error message and a bad lookup.

```python
import starsim_data as ssd
ssd.resolve('USA')            # 'United_States'
ssd.resolve('cote divoire')   # 'Cote_dIvoire'
ssd.resolve('DRC')            # 'Democratic_Republic_of_the_Congo'
ssd.location_info('KE').iso3  # 'KEN'
```
"""

import csv
import unicodedata
import functools as ft
import sciris as sc
import starsim_data as ssd

__all__ = ['resolve', 'location_info', 'list_all_locations', 'parse_level']

# Columns whose values are matched directly, in addition to the `aliases` column.
NAME_COLS = ('location', 'iso_code', 'iso3', 'official_name')

# 0=country, 1=state/province, 2=district, ... (see parse_level). 5 is the finest
# level any of the boundary sources in `starsim_data.shapes` publishes.
MAX_LEVEL = 5


def normalize(name):
    """Collapse a location string to its match key.

    Strips accents, case, punctuation and separator style, so that `'Côte d'Ivoire'`,
    `'cote divoire'` and `'Cote_dIvoire'` all collapse to `cote_divoire`.

    Must stay in step with `normalize` in `scripts/build_locations.py`, which uses it
    to decide which aliases are distinct.
    """
    decomposed = unicodedata.normalize('NFKD', str(name or '').strip())
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = ''.join(' ' if c in '-_/' else c for c in stripped.casefold() if c.isalnum() or c in ' -_/')
    return '_'.join(cleaned.split())


@ft.lru_cache(maxsize=1)
def _table():
    """Load locations.csv, returning (info_by_location, canonical_by_match_key).

    Read with the `csv` module rather than pandas deliberately: pandas' default
    `na_values` turns Namibia's ISO-2 code, the string "NA", into NaN.
    """
    path = sc.thispath(__file__) / 'data' / 'locations.csv'
    info, index = {}, {}
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            location = row['location']
            row['aliases'] = [a for a in row.get('aliases', '').split('|') if a]
            row['level'] = int(row['level'])
            info[location] = sc.objdict(row)
            names = [row[col] for col in NAME_COLS if row.get(col)] + row['aliases']
            for name in names:
                # First writer wins; the build script has already dropped any alias
                # that is ambiguous across locations, so collisions here are benign
                # (e.g. an official name identical to a canonical name).
                index.setdefault(normalize(name), location)
    return info, index


def list_all_locations():
    """Return every canonical location name known to the package, sorted.

    This is the full location table; use `list_locations(which)` for the subset
    actually present in a given dataset.
    """
    info, _ = _table()
    return sorted(info)


def location_info(location):
    """Return the metadata row for a location, as a `sciris.objdict`.

    Args:
        location (str): location name, ISO-2/ISO-3 code, or alias.

    Returns:
        sciris.objdict: with keys `location`, `level`, `iso_code`, `iso3`,
        `official_name`, `aliases`, `primary_contact_source`, `contact_sources`,
        `population_source`.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.location_info('USA').iso3
        'USA'
    """
    info, _ = _table()
    return info[resolve(location)]


def resolve(location, valid=None, dataset=None):
    """Resolve a location string to its canonical key.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name, or alias;
            case-, accent- and punctuation-insensitive.
        valid (collection): if given, the resolved key must be one of these (used to
            scope resolution to the locations actually present in a dataset).
        dataset (str): name of the dataset `valid` came from, for error messages only.

    Returns:
        str: the canonical location key, e.g. `'United_States'`.

    Raises:
        KeyError: if the location is unknown, or is known but absent from `valid`.
            The message lists close matches where there are any.
    """
    _, index = _table()
    key = normalize(location)
    canonical = index.get(key)

    if valid is None:
        if canonical is not None:
            return canonical
        raise KeyError(f'location {location!r} not found{_did_you_mean(location, list_all_locations())}')

    valid = list(valid)
    if canonical in valid:
        return canonical

    # A dataset may hold a key that predates the location table; match it directly
    # rather than insisting every dataset key be registered.
    direct = {normalize(v): v for v in valid}
    if key in direct:
        return direct[key]
    if canonical is None:
        raise KeyError(f'location {location!r} not found{_did_you_mean(location, valid)}')

    # The location is known, but not in this dataset: say so, and where else to find it
    what  = f'{location!r}'
    where = ''
    hint  = ''
    if normalize(canonical) != key:
        what += f' (resolved to {canonical!r})'
    if dataset:
        where = f' in {dataset!r}'
        hint  = f'; see list_locations({dataset!r})'
    errormsg = f'location {what} is not available{where} ({len(valid)} locations{hint}){_elsewhere(canonical, dataset)}'
    raise KeyError(errormsg)


def _elsewhere(location, dataset):
    """Return a fragment naming the other contact sources that do have `location`, if any."""
    info, _ = _table()
    known = ssd.registry.datasets()
    sources = info[location]['contact_sources'].split('|')
    others = [name for name in sources if name and (name != dataset) and (name in known)]
    if (not others) or (dataset not in known) or (known[dataset].layout != 'matrix'):
        return ''

    calls = []
    prem = known.get('prem')
    if prem and (location in prem.locations): # The default contact matrices have it too
        calls.append(f'load({location!r})')
    for name in others:
        func = 'load' if known[name].tier == 0 else 'fetch'
        calls.append(f'{func}({location!r}, which={name!r})')
    return f"; it is in {sc.strjoin(calls, sep=' or ')}"


def _did_you_mean(name, candidates):
    """Return a ' (did you mean ...)' fragment, or '' if nothing is close enough.

    Fuzzy matching is confined to this function: it shapes the error message and
    never influences which location (or dataset) is returned.
    """
    matches = sc.suggest(str(name), list(candidates), n=3, die=False)
    if not matches:
        return ''
    return f' (did you mean: {sc.strjoin(sc.tolist(matches))}?)'


def parse_level(level):
    """Parse an administrative level into an integer.

    Accepts `'admin1'`, `'ADM2'`, `'3'` or a bare `int`. Level 0 is the country;
    higher levels are progressively finer subdivisions (1 = state/province,
    2 = district/county). The upper bound is 5, the finest level any of the boundary
    sources in `starsim_data.shapes` publishes.

    Args:
        level (str/int): the level to parse.

    Returns:
        int: the level number, 0 to 5.

    Raises:
        ValueError: if `level` cannot be parsed or is out of range.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.parse_level('ADM2')
        2
    """
    if isinstance(level, bool):  # bool is an int subclass; not a level
        raise ValueError(f'invalid administrative level {level!r}')
    if isinstance(level, int):
        number = level
    else:
        text = str(level).strip().lower()
        for prefix in ('admin', 'adm', 'level', 'l'):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        if not text.isdigit():
            raise ValueError(f"could not parse administrative level from {level!r}; expected e.g. 'admin1', 'ADM2' or 2")
        number = int(text)
    if not (0 <= number <= MAX_LEVEL):
        raise ValueError(f'administrative level {number} out of range (0 to {MAX_LEVEL})')
    return number
