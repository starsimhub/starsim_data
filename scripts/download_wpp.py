"""
Download UN World Population Prospects (WPP) demographic data via the Data Portal API.

Dev/CI tool -- NOT part of the installed package. Fetches the indicators this package
needs, for its countries, at decadal years 1950-2100, and writes normalized CSVs into
`raw_data/wpp/`. Those CSVs are then consumed by `scripts/build_demographics.py`
(the same builder used for manually-downloaded bulk files), which produces the
bundled HDF5 stores.

Requires a Bearer token in `scripts/.env` (register free at
https://population.un.org/dataportal). The token file is git-ignored. The metadata
(indicator/location) endpoints are open, but the data endpoints require the token.

Usage:

```bash
python scripts/download_wpp.py            # -> raw_data/wpp/wpp_*.csv
python scripts/build_demographics.py --check
```
"""

import argparse
import io
import time
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WPP_OUT = REPO / "raw_data" / "wpp"
LOCATIONS_CSV = REPO / "raw_data" / "locations.csv"
ENV = Path(__file__).resolve().parent / ".env"

API = "https://population.un.org/dataportalapi/api/v1"
YEARS = list(range(1950, 2101, 10))     # decadal snapshots
LOC_CHUNK = 100                         # locations per request (keeps URLs short)

# WPP indicator IDs (see the open /indicators endpoint for the full catalogue).
IND_CBR = 55    # crude birth rate
IND_CNMR = 66   # crude rate of net migration
IND_MX = 79     # age-specific mortality rate m(x,n), 5-year abridged
IND_POP = 46    # population by 5-year age groups and sex


def read_token():
    """Read the Bearer token from scripts/.env (tolerates `TOKEN=...` or a raw header)."""
    if not ENV.is_file():
        raise SystemExit(f"No token file at {ENV}. Add your WPP Bearer token there.")
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if "=" in line and not line.lower().startswith("bearer"):
                line = line.split("=", 1)[1].strip()
            return line if line.lower().startswith("bearer") else f"Bearer {line}"
    raise SystemExit(f"{ENV} is empty")


def get(url, token=None, retries=3):
    """GET a URL, returning decoded text; retries on transient failures."""
    headers = {"Authorization": token} if token else {}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001 -- network flakiness; retry then re-raise
            if attempt == retries - 1:
                raise
            print(f"    retry {attempt+1} after error: {e}")
            time.sleep(2 * (attempt + 1))


def location_ids():
    """Map this package's ISO2 codes to WPP location IDs."""
    import json
    ours = set(pd.read_csv(LOCATIONS_CSV)["iso_code"].str.upper())
    data = json.loads(get(f"{API}/locations/?pageSize=1000"))["data"]
    # Some region aggregates ("Americas", ...) share a country's ISO2 code but have
    # no coordinates; require lat/long so we keep only real countries (one id per ISO2).
    ids = {x["id"]: x["iso2"] for x in data
           if x.get("iso2") in ours and x.get("latitude") is not None}
    missing = ours - set(ids.values())
    if missing:
        print(f"  note: {len(missing)} location(s) not in WPP, skipped: {sorted(missing)}")
    return ids  # {locationId: iso2}


def fetch(token, indicator, loc_ids):
    """Fetch one indicator for all locations across the decade years; return a tidy frame."""
    id_to_iso = loc_ids
    ids = list(loc_ids)
    frames = []
    for year in YEARS:
        for i in range(0, len(ids), LOC_CHUNK):
            chunk = ",".join(str(x) for x in ids[i:i + LOC_CHUNK])
            url = f"{API}/data/indicators/{indicator}/locations/{chunk}/start/{year}/end/{year}?format=csv"
            text = get(url, token)
            df = pd.read_csv(io.StringIO(text), sep="|", skiprows=1)
            frames.append(df)
        print(f"    indicator {indicator}: year {year} done")
    out = pd.concat(frames, ignore_index=True)
    out = out[out["Variant"] == "Median"]
    out["ISO2_code"] = out["LocationId"].map(id_to_iso)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-existing", action="store_true",
                        help="skip any series whose output CSV already exists")
    args = parser.parse_args()

    WPP_OUT.mkdir(parents=True, exist_ok=True)
    token = read_token()
    loc_ids = location_ids()
    print(f"Downloading WPP data for {len(loc_ids)} locations, years {YEARS[0]}-{YEARS[-1]} (decadal)")

    def skip(path):
        if args.skip_existing and path.is_file():
            print(f"  skip existing: {path.name}")
            return True
        return False

    ind_path = WPP_OUT / "wpp_indicators.csv"
    if not skip(ind_path):
        print("  crude birth rate (CBR)...")
        cbr = fetch(token, IND_CBR, loc_ids)[["ISO2_code", "TimeLabel", "Value"]]
        print("  crude net-migration rate (CNMR)...")
        cnmr = fetch(token, IND_CNMR, loc_ids)[["ISO2_code", "TimeLabel", "Value"]]
        ind = cbr.rename(columns={"TimeLabel": "Time", "Value": "CBR"}).merge(
            cnmr.rename(columns={"TimeLabel": "Time", "Value": "CNMR"}),
            on=["ISO2_code", "Time"], how="outer")
        ind.to_csv(ind_path, index=False)
        print(f"  -> wpp_indicators.csv ({len(ind)} rows)")

    lt_path = WPP_OUT / "wpp_lifetable.csv"
    if not skip(lt_path):
        print("  mortality rate (mx, abridged)...")
        mx = fetch(token, IND_MX, loc_ids)
        mx = mx[["ISO2_code", "TimeLabel", "Sex", "AgeStart", "Value"]].rename(
            columns={"TimeLabel": "Time", "AgeStart": "AgeGrpStart", "Value": "mx"})
        mx.to_csv(lt_path, index=False)
        print(f"  -> wpp_lifetable.csv ({len(mx)} rows)")

    pop_path = WPP_OUT / "wpp_population.csv"
    if not skip(pop_path):
        print("  population by 5-year age groups and sex...")
        pop = fetch(token, IND_POP, loc_ids)
        pop = pop[pop["Sex"].isin(["Female", "Male"])]
        wide = pop.pivot_table(index=["ISO2_code", "TimeLabel", "AgeStart"],
                               columns="Sex", values="Value").reset_index()
        wide = wide.rename(columns={"TimeLabel": "Time", "AgeStart": "AgeGrp",
                                    "Female": "PopFemale", "Male": "PopMale"})
        wide.to_csv(pop_path, index=False)
        print(f"  -> wpp_population.csv ({len(wide)} rows)")

    print("Done. Now run: python scripts/build_demographics.py --check")


if __name__ == "__main__":
    main()
