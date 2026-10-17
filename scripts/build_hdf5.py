"""
Build the HDF5 contact-matrix stores from the raw CSV tree.

Dev/CI tool -- NOT part of the installed package. Walks `raw_data/contact_matrices/`
and writes one HDF5 file per dataset (contact source). Each store is keyed by location,
with one dataset per contact layer:

```
prem2021.h5
  /Kenya/all        (n, n) float32
  /Kenya/home
  /Kenya/work
  /Kenya/school
  /Kenya/community
  /United_States/...
  ...
```

Matrices are cast to float32 and written with gzip9 + byte-shuffle (see
reimplementation_plan.md for why this is the size/speed sweet spot). Re-run whenever
the raw data changes; output is overwritten cleanly.

Only `prem2021` is bundled, into `starsim_data/data/`. The other sources are fetched on
demand (tier 1): their stores live in `fetched/` in the repository, outside the wheel,
and `fetch()` downloads each from GitHub at the commit pinned in `PINNED` below,
checking it against the SHA-256 in the manifest `starsim_data/data/fetched.json`. The
manifest is rewritten on every run, from the stores in `fetched/`.

A store is stamped with its build time, so rebuilding one changes its bytes. The fetched
stores are therefore rebuilt only with `--fetched`; afterwards commit and push the new
store, then set its commit in `PINNED` and run this script again, so that the manifest's
URL serves the bytes its SHA-256 describes.

Usage:

```bash
python scripts/build_hdf5.py              # build prem2021.h5 and rewrite the manifest
python scripts/build_hdf5.py --check      # also round-trip validate against CSVs
python scripts/build_hdf5.py --fetched    # also rebuild the stores in fetched/
```
"""

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from provenance import stamp

REPO = Path(__file__).resolve().parent.parent
CONTACT = REPO / "raw_data" / "contact_matrices"
OUT = REPO / "starsim_data" / "data"
FETCHED = REPO / "fetched"
MANIFEST = OUT / "fetched.json"

# The contact sources bundled in the wheel; every other source is fetched on demand.
BUNDLED = ["prem2021"]

# Where each fetched store is downloaded from: a commit on GitHub, and the store's path
# at that commit. The bytes there must be those of the store in fetched/.
URL = "https://raw.githubusercontent.com/starsimhub/starsim_data/{commit}/{path}"
PINNED = {
    "prem2017": dict(commit="56cb6a5d1ec502d4308d748506f98054c107c8f6",
                     path="starsim_data/data/prem2017.h5"),
    "mistry2021": dict(commit="56cb6a5d1ec502d4308d748506f98054c107c8f6",
                       path="starsim_data/data/mistry2021.h5"),
}
DESCRIPTION = "Age-structured contact matrix by setting"

# Machine-readable counterpart to NOTICE.md, written into each store so that the
# attribution travels with the data rather than only with the repository.
SOURCES = {
    "prem2017": dict(
        source="Prem et al. 2017",
        source_url="https://github.com/kieshaprem/synthetic-contact-matrices",
        via="https://github.com/epistorm/epydemix-data",
        license="GPL-3.0",
        citation=("Prem K, Cook AR, Jit M. Projecting social contact matrices in 152 "
                  "countries using contact surveys and demographic data. PLoS Comput Biol "
                  "13(9): e1005697 (2017)."),
        note="16x16 matrices; 5-year age groups (0-4, 5-9, ..., 75+).",
    ),
    "prem2021": dict(
        source="Prem et al. 2021",
        source_url="https://github.com/kieshaprem/synthetic-contact-matrices",
        via="https://github.com/epistorm/epydemix-data",
        license="GPL-3.0",
        citation=("Prem K, Zandvoort K van, Klepac P, et al. Projecting contact matrices "
                  "in 177 geographical regions: An update and comparison with empirical "
                  "data for the COVID-19 era. PLoS Comput Biol 17(7): e1009098 (2021)."),
        note="16x16 matrices; 5-year age groups (0-4, 5-9, ..., 75+).",
    ),
    "mistry2021": dict(
        source="Mistry et al. 2021",
        source_url="https://github.com/mobs-lab/mixing-patterns",
        via="https://github.com/epistorm/epydemix-data",
        license="Apache-2.0",
        citation=("Mistry D, Litvinova M, Pastore y Piontti A, et al. Inferring "
                  "high-resolution human mixing patterns for disease modeling. Nature "
                  "Communications 12, 323 (2021)."),
        note="85x85 matrices; single-year age groups (0-84, last group is 84+).",
    ),
}

# Contact layers, in a stable order. Each is a `{source}_contacts_{kind}.csv` file.
KINDS = ["all", "home", "work", "school", "community"]

# Width (in years) of each source's age bins, used to label the matrix axes with the
# start age of each bin (e.g. prem's 16 bins -> 0, 5, ..., 75). Sources not listed here
# fall back to a positional 0..n-1 axis.
AGE_WIDTH = {"prem2017": 5, "prem2021": 5, "mistry2021": 1}

# HDF5 dataset creation options: float32 + gzip9 + byte-shuffle. Chunk = one matrix.
H5OPTS = dict(compression="gzip", compression_opts=9, shuffle=True)


def discover_sources():
    """Return the sorted set of contact sources present in the raw tree (e.g. prem2017)."""
    sources = set()
    for csv in CONTACT.glob("*/*_contacts_all.csv"):
        sources.add(csv.name.split("_contacts_")[0])
    return sorted(sources)


def read_matrix(path):
    """Read a headerless contact-matrix CSV as a float32 array."""
    return pd.read_csv(path, header=None).to_numpy(dtype=np.float32)


def _ages(source, n):
    """Return the start age of each of the `n` age bins for `source` (or None if unknown)."""
    width = AGE_WIDTH.get(source)
    if width is None:
        return None
    return [i * width for i in range(n)]


def build_source(source, check=False):
    """Write `<source>.h5` for one contact source: into the package if bundled, else `fetched/`."""
    out_path = (OUT if source in BUNDLED else FETCHED) / f"{source}.h5"
    n_locations = 0
    ages = None
    with h5py.File(out_path, "w") as f:
        for loc_dir in sorted(p for p in CONTACT.iterdir() if p.is_dir()):
            location = loc_dir.name
            wrote_any = False
            for kind in KINDS:
                csv = loc_dir / f"{source}_contacts_{kind}.csv"
                if not csv.exists():
                    continue
                mat = read_matrix(csv)
                if ages is None:
                    ages = _ages(source, mat.shape[0])
                f.create_dataset(f"{location}/{kind}", data=mat, **H5OPTS)
                if check:
                    back = f[f"{location}/{kind}"][:]
                    assert np.allclose(back, mat, rtol=1e-6), f"mismatch: {csv}"
                wrote_any = True
            if wrote_any:
                n_locations += 1
        spec = {"layout": "matrix"}
        if ages is not None:
            spec["ages"] = ages
        f.attrs["spec"] = json.dumps(spec)
        if source not in SOURCES:
            print(f"  WARNING: no attribution recorded for {source!r}; add it to SOURCES "
                  f"in this script and to NOTICE.md")
        f.attrs["provenance"] = json.dumps(
            stamp(source, "scripts/build_hdf5.py", n_locations=n_locations,
                  **SOURCES.get(source, {})))
    size_mb = out_path.stat().st_size / 1e6
    print(f"  {out_path.name}: {n_locations} locations, {size_mb:.1f} MB")


def sha256(path):
    """The SHA-256 of a file, as `fetch()` checks it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(sources):
    """Describe each fetched store (from its file in `fetched/`) in `data/fetched.json`."""
    manifest = {}
    for source in sources:
        if source in BUNDLED:
            continue
        path = FETCHED / f"{source}.h5"
        if source not in PINNED:
            raise ValueError(f"{source!r} is fetched but has no commit in PINNED; push its "
                             f"store and add it")
        with h5py.File(path, "r") as f:
            spec = json.loads(f.attrs["spec"])
            manifest[source] = dict(store=path.name,
                                    url=URL.format(**PINNED[source]),
                                    sha256=sha256(path),
                                    bytes=path.stat().st_size,
                                    layout=spec["layout"],
                                    description=DESCRIPTION,
                                    locations=sorted(f.keys()),
                                    provenance=json.loads(f.attrs["provenance"]))
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"  {MANIFEST.name}: {len(manifest)} fetched store(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="round-trip validate HDF5 values against the source CSVs")
    parser.add_argument("--fetched", action="store_true",
                        help="also rebuild the stores in fetched/ (then repin them in PINNED)")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    FETCHED.mkdir(parents=True, exist_ok=True)
    sources = discover_sources()
    print(f"Found {len(sources)} dataset(s) in {CONTACT}: {', '.join(sources)}")
    for source in sources:
        if source in BUNDLED or args.fetched:
            build_source(source, check=args.check)
    write_manifest(sources)
    if args.fetched:
        print("The fetched stores were rebuilt: commit and push them, set their commit in "
              "PINNED, and run this script again.")
    print("Done.")


if __name__ == "__main__":
    main()
