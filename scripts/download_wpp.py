"""
Download UN World Population Prospects (WPP) demographic data via the Data Portal API.

Dev/CI tool -- NOT part of the installed package. Fetches the indicators this package
needs, for its countries, at decadal years 1950-2100, and writes normalized CSVs into
`raw_data/demographics/`. Those CSVs are then consumed by `scripts/build_demographics.py`
(the same builder used for manually-downloaded bulk files), which produces the
bundled HDF5 stores.

Requires a Bearer token in `scripts/.env` (register free at
https://population.un.org/dataportal). The token file is git-ignored. The metadata
(indicator/location) endpoints are open, but the data endpoints require the token.

Usage:

```bash
python scripts/download_wpp.py            # -> raw_data/demographics/wpp_*.csv
python scripts/build_demographics.py --check
```
"""

import argparse
import io
import json
import time
import pandas as pd
import sciris as sc

REPO          = sc.thispath(__file__).parent
WPP_OUT       = REPO / 'raw_data' / 'demographics'
LOCATIONS_CSV = REPO / 'starsim_data' / 'data' / 'locations.csv' # Canonical, bundled
ENV           = sc.thispath(__file__) / '.env'

API = 'https://population.un.org/dataportalapi/api/v1'
YEARS = list(range(1950, 2101, 10))     # decadal snapshots
LOC_CHUNK = 100                         # locations per request (keeps URLs short)

# WPP indicator IDs (see the open /indicators endpoint for the full catalog).
IND_CBR  = 55 # Crude birth rate
IND_CNMR = 66 # Crude rate of net migration
IND_MX   = 79 # Age-specific mortality rate m(x,n), 5-year abridged
IND_POP  = 46 # Population by 5-year age groups and sex
IND_ASFR = 17 # Fertility rates by age of mother, 5-year (births per 1,000 women)


def read_token():
    """ Read the Bearer token from scripts/.env (tolerates `TOKEN=...` or a raw header)."""
    if not ENV.is_file():
        raise SystemExit(f'No token file at {ENV}. Add your WPP Bearer token there.')
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            if '=' in line and not line.lower().startswith('bearer'):
                line = line.split('=', 1)[1].strip()
            return line if line.lower().startswith('bearer') else f'Bearer {line}'
    raise SystemExit(f'{ENV} is empty')


def get(url, token=None, retries=3):
    """ GET a URL, returning decoded text; retries on transient failures """
    headers = {'Authorization': token} if token else {}
    for attempt in range(retries):
        try:
            return sc.urlopen(url, headers=headers, timeout=180, die=True)
        except Exception as e: # Any failure may be network flakiness, so retry, then re-raise
            if attempt == retries - 1:
                raise
            print(f'    retry {attempt+1} after error: {e}')
            time.sleep(2 * (attempt + 1))
    return


def location_ids():
    """ Map this package's ISO2 codes to WPP location IDs """
    # keep_default_na=False: Namibia's ISO-2 code is the string "NA", which pandas
    # would otherwise read as NaN, silently excluding Namibia from the download.
    locations = pd.read_csv(LOCATIONS_CSV, keep_default_na=False, na_values=[])
    ours = set(locations['iso_code'].str.upper())
    data = json.loads(get(f'{API}/locations/?pageSize=1000'))['data']
    # Some region aggregates ("Americas", ...) share a country's ISO2 code but have
    # no coordinates; require lat/long so we keep only real countries (one id per ISO2).
    ids = {x['id']: x['iso2'] for x in data if (x.get('iso2') in ours) and (x.get('latitude') is not None)}
    missing = ours - set(ids.values())
    if missing:
        print(f'  note: {len(missing)} location(s) not in WPP, skipped: {sorted(missing)}')
    return ids # {locationId: iso2}


def fetch(token, indicator, loc_ids):
    """ Fetch one indicator for all locations across the decade years; return a tidy frame """
    ids = list(loc_ids)
    frames = []
    for year in YEARS:
        for i in range(0, len(ids), LOC_CHUNK):
            chunk = ','.join(str(x) for x in ids[i:i + LOC_CHUNK])
            url = f'{API}/data/indicators/{indicator}/locations/{chunk}/start/{year}/end/{year}?format=csv'
            text = get(url, token)
            df = pd.read_csv(io.StringIO(text), sep='|', skiprows=1)
            frames.append(df)
        print(f'    indicator {indicator}: year {year} done')
    out = pd.concat(frames, ignore_index=True)
    out = out[out['Variant'] == 'Median']
    out['ISO2_code'] = out['LocationId'].map(loc_ids)
    return out


def skip(path, skip_existing):
    """ Whether to skip writing `path`, because it exists and --skip-existing was given """
    if skip_existing and path.is_file():
        print(f'  skip existing: {path.name}')
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--skip-existing', action='store_true', help='skip any series whose output CSV already exists')
    args = parser.parse_args()

    WPP_OUT.mkdir(parents=True, exist_ok=True)
    token = read_token()
    loc_ids = location_ids()
    print(f'Downloading WPP data for {len(loc_ids)} locations, years {YEARS[0]}-{YEARS[-1]} (decadal)')

    ind_path = WPP_OUT / 'wpp_indicators.csv'
    if not skip(ind_path, args.skip_existing):
        print('  crude birth rate (CBR)...')
        cbr = fetch(token, IND_CBR, loc_ids)[['ISO2_code', 'TimeLabel', 'Value']]
        print('  crude net-migration rate (CNMR)...')
        cnmr = fetch(token, IND_CNMR, loc_ids)[['ISO2_code', 'TimeLabel', 'Value']]
        cbr  = cbr.rename(columns={'TimeLabel': 'Time', 'Value': 'CBR'})
        cnmr = cnmr.rename(columns={'TimeLabel': 'Time', 'Value': 'CNMR'})
        ind = cbr.merge(cnmr, on=['ISO2_code', 'Time'], how='outer')
        ind.to_csv(ind_path, index=False)
        print(f'  -> wpp_indicators.csv ({len(ind)} rows)')

    lt_path = WPP_OUT / 'wpp_lifetable.csv'
    if not skip(lt_path, args.skip_existing):
        print('  mortality rate (mx, abridged)...')
        mx = fetch(token, IND_MX, loc_ids)
        mx = mx[['ISO2_code', 'TimeLabel', 'Sex', 'AgeStart', 'Value']]
        mx = mx.rename(columns={'TimeLabel': 'Time', 'AgeStart': 'AgeGrpStart', 'Value': 'mx'})
        mx.to_csv(lt_path, index=False)
        print(f'  -> wpp_lifetable.csv ({len(mx)} rows)')

    pop_path = WPP_OUT / 'wpp_population.csv'
    if not skip(pop_path, args.skip_existing):
        print('  population by 5-year age groups and sex...')
        pop = fetch(token, IND_POP, loc_ids)
        pop = pop[pop['Sex'].isin(['Female', 'Male'])]
        wide = pop.pivot_table(index=['ISO2_code', 'TimeLabel', 'AgeStart'], columns='Sex', values='Value').reset_index()
        wide = wide.rename(columns={'TimeLabel': 'Time', 'AgeStart': 'AgeGrp', 'Female': 'PopFemale', 'Male': 'PopMale'})
        wide.to_csv(pop_path, index=False)
        print(f'  -> wpp_population.csv ({len(wide)} rows)')

    fert_path = WPP_OUT / 'wpp_fertility.csv'
    if not skip(fert_path, args.skip_existing):
        print('  age-specific fertility rate (ASFR, 5-year)...')
        asfr = fetch(token, IND_ASFR, loc_ids)
        asfr = asfr[['ISO2_code', 'TimeLabel', 'AgeStart', 'Value']]
        asfr = asfr.rename(columns={'TimeLabel': 'Time', 'AgeStart': 'AgeGrpStart', 'Value': 'ASFR'})
        asfr.to_csv(fert_path, index=False)
        print(f'  -> wpp_fertility.csv ({len(asfr)} rows)')

    print('Done. Now run: python scripts/build_demographics.py --check')
    return


if __name__ == '__main__':
    main()
