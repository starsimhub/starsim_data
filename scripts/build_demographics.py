"""
Build the bundled demographic HDF5 stores from UN World Population Prospects (WPP) CSVs.

Dev/CI tool -- NOT part of the installed package. Reads the WPP bulk CSV files you
place in `raw_data/demographics/` (see that folder's README for what to download),
filters them to the countries this package ships (by ISO2 code) and to decadal years
1950-2100, and writes a single `starsim_data/data/demographics.h5` with one group per
series (each carrying its own `spec` describing its layout):

- `/births`     -- crude birth rate (CBR), one value per year.
- `/migration`  -- crude net-migration rate (CNMR), one value per year.
- `/deaths`     -- age/sex-specific mortality rate (mx), 5-year abridged bins.
- `/population` -- population by 5-year age groups and sex (absolute persons).

Input files are classified by their columns, not their names, so whichever exact WPP
files you download will be routed correctly as long as they contain the expected
columns. Re-run whenever the raw data changes; output is overwritten cleanly.

Usage:

```bash
python scripts/build_demographics.py                 # read raw_data/demographics/
python scripts/build_demographics.py --wpp DIR        # read a different input dir
python scripts/build_demographics.py --check          # round-trip validate via the loader
```
"""

import argparse
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_WPP = REPO / "raw_data" / "demographics"
OUT = REPO / "starsim_data" / "data"
LOCATIONS_CSV = OUT / "locations.csv"      # canonical, bundled with the package

YEARS = list(range(1950, 2101, 10))     # decadal snapshots, per the plan
SEXES = ["Female", "Male"]              # drop WPP's "Total"; matches ss.Deaths sex_keys

H5OPTS = dict(compression="gzip", compression_opts=9, shuffle=True)


def iso2_to_name():
    """Map ISO2 code -> this package's location (folder) name, from locations.csv."""
    df = pd.read_csv(LOCATIONS_CSV)
    return dict(zip(df["iso_code"].str.upper(), df["location"]))


def classify(cols):
    """Identify a WPP file from its column set. Returns a type tag or None."""
    cols = set(cols)
    if {"Time", "CBR", "CNMR"} <= cols:
        return "indicators"
    if {"Time", "Sex", "AgeGrpStart", "mx"} <= cols:
        return "lifetable"
    if {"Time", "PopMale", "PopFemale"} <= cols and ({"AgeGrp"} & cols or {"AgeGrpStart"} & cols):
        return "population"
    return None


def _iso_col(cols):
    for c in ("ISO2_code", "ISO2Code", "Iso2"):
        if c in cols:
            return c
    raise ValueError("WPP file has no ISO2 column; cannot map to package locations")


def _load_by_type(wpp_dir):
    """Read every WPP CSV in `wpp_dir`, grouped by file type, filtered to our locations/years."""
    name_map = iso2_to_name()
    grouped = {"indicators": [], "lifetable": [], "population": []}
    files = sorted(p for p in wpp_dir.glob("*.csv")) + sorted(wpp_dir.glob("*.csv.gz"))
    if not files:
        raise SystemExit(f"No CSV files found in {wpp_dir} -- see {wpp_dir}/README.md")

    for path in files:
        header = pd.read_csv(path, nrows=0).columns
        kind = classify(header)
        if kind is None:
            print(f"  skip (unrecognized): {path.name}")
            continue
        iso = _iso_col(header)
        if kind == "indicators":
            cols = [iso, "Time", "CBR", "CNMR"]
        elif kind == "lifetable":
            cols = [iso, "Time", "Sex", "AgeGrpStart", "mx"]
        else:
            age = "AgeGrp" if "AgeGrp" in header else "AgeGrpStart"
            cols = [iso, "Time", age, "PopMale", "PopFemale"]

        df = pd.read_csv(path, usecols=cols)
        df = df[df["Time"].isin(YEARS)].rename(columns={iso: "ISO2"})
        df["ISO2"] = df["ISO2"].str.upper()
        df = df[df["ISO2"].isin(name_map)]
        df["location"] = df["ISO2"].map(name_map)
        grouped[kind].append(df)
        print(f"  read {path.name} -> {kind} ({len(df)} rows kept)")

    return {k: pd.concat(v, ignore_index=True) for k, v in grouped.items() if v}


def write_crude(root, series, df, value_col):
    """Write a one-value-per-year series (births/migration) as a group of demographics.h5."""
    grp = root.create_group(series)
    grp.attrs["spec"] = json.dumps({"layout": "crude", "years": YEARS, "value_col": value_col})
    for location, sub in df.groupby("location"):
        sub = sub.drop_duplicates("Time")
        vals = sub.set_index("Time")[value_col].reindex(YEARS).to_numpy(np.float32)
        grp.create_dataset(location, data=vals, **H5OPTS)
    print(f"  /{series}: {len(grp)} locations")


def write_year_sex_age(root, series, df, value_col, age_col, layout):
    """Write a (year, sex, age) array per location (deaths/population) as a group."""
    df = df[df["Sex"].isin(SEXES)] if "Sex" in df else df
    ages = sorted(df[age_col].unique())
    idx_cols = ["Time", "Sex", age_col]
    grp = root.create_group(series)
    grp.attrs["spec"] = json.dumps({"layout": layout, "years": YEARS, "sexes": SEXES,
                                    "ages": [int(a) for a in ages],
                                    "age_col": age_col, "value_col": value_col})
    full = pd.MultiIndex.from_product([YEARS, SEXES, ages], names=idx_cols)
    for location, sub in df.groupby("location"):
        s = sub.set_index(idx_cols)[value_col]
        s = s[~s.index.duplicated()].reindex(full)
        arr = s.to_numpy(np.float32).reshape(len(YEARS), len(SEXES), len(ages))
        grp.create_dataset(location, data=arr, **H5OPTS)
    print(f"  /{series}: {len(grp)} locations")


def build(wpp_dir, check=False):
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Reading WPP CSVs from {wpp_dir}")
    data = _load_by_type(wpp_dir)

    out_path = OUT / "demographics.h5"
    with h5py.File(out_path, "w") as f:
        if "indicators" in data:
            write_crude(f, "births", data["indicators"], "CBR")
            write_crude(f, "migration", data["indicators"], "CNMR")
        if "lifetable" in data:
            write_year_sex_age(f, "deaths", data["lifetable"], "mx", "AgeGrpStart", "mortality")
        if "population" in data:
            pop = data["population"]
            age_col = "AgeGrp" if "AgeGrp" in pop else "AgeGrpStart"
            pop[age_col] = pd.to_numeric(pop[age_col].astype(str).str.rstrip("+"), errors="coerce")
            pop = pop.dropna(subset=[age_col])
            pop[age_col] = pop[age_col].astype(int)
            long = pop.melt(id_vars=["location", "Time", age_col],
                            value_vars=["PopFemale", "PopMale"], var_name="Sex", value_name="Value")
            long["Sex"] = long["Sex"].map({"PopFemale": "Female", "PopMale": "Male"})
            write_year_sex_age(f, "population", long.rename(columns={age_col: "AgeGrp"}),
                               "Value", "AgeGrp", "population")
    print(f"  demographics.h5: {out_path.stat().st_size/1e6:.2f} MB")

    if check:
        import sys
        sys.path.insert(0, str(REPO))
        import starsim_data as ssd
        for which in ("births", "migration", "deaths", "population"):
            if which in ssd.list_datasets():
                loc = ssd.list_locations(which)[0]
                df = ssd.load(loc, which=which)
                assert len(df) > 0, which
                print(f"  check {which}: load({loc!r}) -> {df.shape}, cols={list(df.columns)}")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wpp", type=Path, default=DEFAULT_WPP, help="input dir of WPP CSVs")
    parser.add_argument("--check", action="store_true", help="round-trip validate via the loader")
    args = parser.parse_args()
    build(args.wpp, check=args.check)


if __name__ == "__main__":
    main()
