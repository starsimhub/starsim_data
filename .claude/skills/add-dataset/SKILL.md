---
name: add-dataset
description: Add a new data source to starsim_data — another country's subnational data, a new contact source, populations, commuting or mobility flows, or any other dataset — by writing its download script and build step and wiring it into the registry, provenance, docs and tests. Use when asked to add, import or package data for a new location or source (e.g. "add Germany's districts", "import Canada's provinces from epydemix", "add the commuter matrix").
---

# Add a dataset to starsim_data

A dataset here is three things: a **download script** that copies the upstream data into `raw_data/` as readable CSVs, a **build step** that turns those CSVs into a self-describing HDF5 store, and the **wiring** (license, docs, tests) that the repo's invariants require. The US states (`mistry2021_us`, `population_us`) are the worked example to copy: `scripts/download_epydemix.py`, and `build_population_us()` and the tables at the top of `scripts/build_hdf5.py`.

Read `CLAUDE.md` first: the tier invariant, the registry, and "Keeping the docs in step" all apply.

## 1. Settle these before writing code

Ask Cliff about any of these you can't answer from the source itself. They decide everything after.

- **License.** Find the exact license of the data (not of the repo it sits in: epydemix-data is GPL-3.0 as a whole, but its Census numbers are public domain). If it can't be redistributed, it can't be a store here; it can only be fetched from upstream at use time, as GADM is (`redistributable=False`). Record the license as it will appear in `NOTICE.md`.
- **Tier.** Bundled (tier 0, in the wheel) only if it is small and most users need it; Cliff wants the wheel's size unchanged unless he agrees otherwise. Everything else is a fetched store (tier 1) in `fetched/`.
- **Location keys.** A subnational unit is keyed `<Country>:<Unit>`, and the key must be the unit's `dot_name` in the node table, so that `resolve()`, `load_nodes()` and the new data agree. Check with `ssd.load_nodes(country, level=1).dot_name`. Only levels 0 and 1 are bundled. For level 2 and finer, get the names from `ssd.fetch_nodes(country, level=2)` (needs `[spatial]`), and if the source's names don't match them (e.g. `Landkreis Harburg` against `Harburg`), build a crosswalk from codes rather than fuzzy-matching names. Commit the crosswalk as a CSV in `raw_data/`.
- **Layout.** Reuse one if it fits: `matrix` (square, by age), `population` and `mortality` (a year × sex × age array), `crude` (one value per year), `nodes`. A new shape, such as origin–destination flows, needs a new shaper in `starsim_data/loaders.py`, registered with `ssd.registry.register_layout()` and documented in `docs/08-architecture.qmd`. Return the same columns an existing dataset returns wherever the meaning is the same: `population_us` uses `population`'s `Time, Sex, AgeGrp, Value`, with `Sex='Both sexes'` because the source doesn't split by sex.
- **Name.** Lowercase, source then scope: `mistry2021_us`, `population_us`. Don't put new locations into a store that is already published (for example, adding states to `mistry2021`): it changes the store's bytes, and its pinned download, for everyone.
- **Upstream version.** Pin a commit, release or vintage, so that rerunning the download gives the same files.

## 2. Download script: `scripts/download_<source>.py`

Model it on `scripts/download_epydemix.py`:

- A module docstring saying what it downloads, from where, into which files, and the command to run next.
- The upstream version pinned in a constant (`COMMIT = ...`), and URLs built from it.
- Output to `raw_data/`, as plain CSVs a person can read and diff: contact matrices as `raw_data/contact_matrices/<Country>__<Unit>/<source>_contacts_<kind>.csv` (headerless, square; the `__` stands for `:`, which isn't legal in a folder name everywhere), and anything else as one tidy CSV keyed by `location` (e.g. `raw_data/population_us.csv`: `location, age, population`).
- Check every location against the node table before writing anything, and raise, listing the ones that don't match.
- Any token goes in `scripts/.env` (git-ignored), as `download_wpp.py` does, and never in the code.
- Read every CSV with `keep_default_na=False` or the `csv` module (Namibia's ISO-2 code is `NA`).
- Keep downloading separate from building, so that the build and its `--check` run offline from the committed CSVs.

Tell Cliff how big the download and the raw CSVs will be before running it. Raw CSVs are committed, so 30 MB of them is 30 MB in git history.

## 3. Build step

All fetched stores are listed in `scripts/build_hdf5.py`, which writes the manifest `starsim_data/data/fetched.json` from them. Add the new store there:

- `PINNED[name] = dict(commit='main', path='fetched/<name>.h5')`. It stays `'main'` until the store is on `main` on GitHub; then Cliff sets the real commit (the build warns until then).
- `SOURCES[name]`: `source`, `source_url`, `via` (if it came through another project), `license`, `citation`, `note`. This is written into the store as its provenance.
- `DESCRIPTIONS[name]`: one line for `list_datasets()`.
- Contact matrices need nothing more than their CSVs and an `AGE_WIDTH` entry: sources are discovered from the file names.
- Anything else needs a `build_<name>(check=False)` function, like `build_population_us()`. It writes one dataset per location key and a root `spec` attribute for the layout, for example `dict(layout='population', years=[...], sexes=[...], ages=[...], age_col='AgeGrp', value_col='Value')`, plus `provenance` from `stamp()`. Under `check`, it reads each value back and compares it with its CSV. Call it from `main()` when its name is passed to `--fetched`.
- A bundled store goes into `starsim_data/data/` instead, needs an entry in `registry.DESCRIPTIONS`, and is discovered from its file. Bundling something new is Cliff's call (see Tier).

Build only the new store: `python scripts/build_hdf5.py --check --fetched <name>`. Never rebuild a published store, since that changes its bytes and breaks its pinned download. Every run also rewrites the bundled `prem2021.h5` and `prem/prem2017.h5`, with a new build time and the same data, so restore them afterwards with `git restore starsim_data/data/prem2021.h5 starsim_data/data/prem/prem2017.h5` unless their data really changed.

Levels are worked out from the keys (`United_States:Massachusetts` is level 1). `fetch()` reads any fetched store with no further code, and `load()` points to it from other datasets of the same layout ("it is in fetch(...)").

## 4. Wiring

Everything below is required: the tests check some of it, and none of it updates itself.

- `NOTICE.md`: a section for a new source (or a bullet under the existing one for the same study), and the list of fetched stores in its introduction.
- `tests/test_provenance.py::test_licenses`: the new dataset and its license.
- Tests: one compact test of what's new, like `tests/test_load.py::test_us_states` (shape, schema, a sanity total, and the error that points to it). The offline suite reads fetched stores from `fetched/` through `tests/conftest.py`, so no network is needed. Update `tests/README.md` if a file's coverage changes.
- Docs: `docs/03-datasets.qmd` (the schema and an example; downloading examples must be static ```` ```python ```` blocks), `docs/06-datasources.qmd` (coverage, license, limitations), `docs/02-tiers.qmd` (the tier table), `docs/10-building-the-data.qmd`, and `docs/04-locations.qmd` if naming changes. Update the comparison table in `docs/07-related-projects.qmd` if coverage changes.
- `README.md` (the source table), `CHANGELOG.md` (one line), `raw_data/README.md`, `scripts/README.md`, and the commands in `CLAUDE.md`.

## 5. Check

```bash
python scripts/build_hdf5.py --check
pytest -m "not network"
pytest tests/test_docs.py
great-docs build    # if Quarto is available
```

Then try it the way a user would, including the errors: a misspelled unit, a unit the dataset lacks, and an argument that doesn't apply (it must be rejected, not ignored). Don't commit; leave everything for Cliff, and say which `PINNED` commits need setting once the stores are on `main`.

## Worked sketch: Germany's districts (not built yet)

Requested for MEmilio users: the roughly 400 districts (Kreise), with populations by age group, centroids, and the commuter matrix between them. Verify every URL, table number and license below before relying on it.

- **Populations:** Destatis GENESIS-Online, table 12411-0017 (population by district and age group) or its successor. The API needs an account; put the token in `scripts/.env`. The license is probably Datenlizenz Deutschland – Namensnennung 2.0 (`dl-de/by-2-0`), which allows redistribution with attribution. Use the `population` layout with Germany's age groups, keyed `Germany:<Kreis>`.
- **Commuter flows:** the Federal Employment Agency's commuter statistics (Pendlerstatistik), one spreadsheet per state. MEmilio's `getCommuterMobility` (in `memilio.epidata`) shows the URLs and how to parse them. Check the agency's terms of reuse. This needs a new layout, e.g. `flows`, returning `origin, destination, value` for a location (`Germany`), from a sparse array stored as three columns.
- **Keys:** districts are identified by their AGS code (Amtlicher Gemeindeschlüssel). Get the level-2 `dot_name`s from `fetch_nodes('Germany', level=2)` and crosswalk AGS to `dot_name`, using codes where the boundary source has them and a committed crosswalk CSV where it doesn't.
- **Places:** `load_nodes('Germany', level=2)` needs level 2 in the bundled node table, which is a `scripts/build_nodes.py` change and a size decision for Cliff. Otherwise `fetch_nodes()` already gives centroids at level 2.
- **Size:** about 400 × 400 sparse flows and 400 × (6–21) age groups, so a fetched store of well under 1 MB.
