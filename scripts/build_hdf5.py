"""
Build the bundled HDF5 contact-matrix stores from the raw CSV tree.

Dev/CI tool -- NOT part of the installed package. Walks ``raw_data/`` and writes
one HDF5 file per dataset (contact source) into ``starsim_data/data/``, plus a copy
of ``locations.csv``. Each store is keyed by location, with one dataset per contact
layer::

    prem2017.h5
      /Kenya/all        (n, n) float32
      /Kenya/home
      /Kenya/work
      /Kenya/school
      /Kenya/community
      /United_States/...
      ...

Matrices are cast to float32 and written with gzip9 + byte-shuffle (see
reimplementation_plan.md for why this is the size/speed sweet spot). Re-run whenever
the raw data changes; output is overwritten cleanly.

Usage::

    python scripts/build_hdf5.py            # build all datasets found in raw_data
    python scripts/build_hdf5.py --check    # also round-trip validate against CSVs
"""

import argparse
import shutil
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "raw_data"
OUT = REPO / "starsim_data" / "data"

# Contact layers, in a stable order. Each is a `{source}_contacts_{kind}.csv` file.
KINDS = ["all", "home", "work", "school", "community"]

# HDF5 dataset creation options: float32 + gzip9 + byte-shuffle. Chunk = one matrix.
H5OPTS = dict(compression="gzip", compression_opts=9, shuffle=True)


def discover_sources():
    """Return the sorted set of contact sources present in the raw tree (e.g. prem2017)."""
    sources = set()
    for csv in RAW.glob("*/*_contacts_all.csv"):
        sources.add(csv.name.split("_contacts_")[0])
    return sorted(sources)


def read_matrix(path):
    """Read a headerless contact-matrix CSV as a float32 array."""
    return pd.read_csv(path, header=None).to_numpy(dtype=np.float32)


def build_source(source, check=False):
    """Write ``starsim_data/data/<source>.h5`` for one contact source."""
    out_path = OUT / f"{source}.h5"
    n_locations = 0
    with h5py.File(out_path, "w") as f:
        for loc_dir in sorted(p for p in RAW.iterdir() if p.is_dir()):
            location = loc_dir.name
            wrote_any = False
            for kind in KINDS:
                csv = loc_dir / f"{source}_contacts_{kind}.csv"
                if not csv.exists():
                    continue
                mat = read_matrix(csv)
                f.create_dataset(f"{location}/{kind}", data=mat, **H5OPTS)
                if check:
                    back = f[f"{location}/{kind}"][:]
                    assert np.allclose(back, mat, rtol=1e-6), f"mismatch: {csv}"
                wrote_any = True
            if wrote_any:
                n_locations += 1
    size_mb = out_path.stat().st_size / 1e6
    print(f"  {out_path.name}: {n_locations} locations, {size_mb:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="round-trip validate HDF5 values against the source CSVs")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    sources = discover_sources()
    print(f"Found {len(sources)} dataset(s) in {RAW}: {', '.join(sources)}")
    for source in sources:
        build_source(source, check=args.check)

    shutil.copyfile(RAW / "locations.csv", OUT / "locations.csv")
    print(f"  locations.csv -> {OUT / 'locations.csv'}")
    print("Done.")


if __name__ == "__main__":
    main()
