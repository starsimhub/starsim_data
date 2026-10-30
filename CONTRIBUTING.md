# Contributing

How to change `starsim_data` and release it. Every change goes through a pull request to `main`; nothing is committed to `main` directly.

## Setting up

```bash
git clone https://github.com/starsimhub/starsim_data
cd starsim_data
pip install -e ".[dev]"     # add ,spatial to rebuild the node table
pytest -m "not network"     # the offline suite, as CI runs it
```

## Changing code

Make the change on a branch, with a test if it fixes or adds something, and update the prose it affects: the API reference regenerates itself, but the pages in `docs/user-guide/` don't. A new dataset or source also touches `docs/user-guide/03-datasets.qmd`, `docs/user-guide/06-datasources.qmd` and `NOTICE.md` (a test checks the licenses there against the data).

## Building the documentation

The documentation is built with [Sciris' fork of great-docs](https://github.com/sciris/great-docs) and [quartopydoc](https://pypi.org/project/quartopydoc/), which the `docs` dependency group installs, plus [Quarto](https://quarto.org/docs/get-started/):

```bash
pip install -e ".[dev]" --group docs
great-docs build      # -> docs/_site/
docs/render           # the same, rendering pages in parallel
great-docs preview    # live reload on http://localhost:3000
```

Adding a page means adding a `.qmd` file to `docs/user-guide/` with a `title` and a `guide-section`; there is no navigation configuration to update (a new module, though, needs adding to the `quartodoc:` sections in `docs/great-docs.yml`). `docs/user-guide/assets/starsim-theme.html` holds the style overrides that make the site look like the Starsim docs.

## Changing data

The `.h5` files are build artifacts: never edit them by hand. Edit the sources in `raw_data/` and rebuild with the scripts in `scripts/` (its README describes each), checking the result with `--check`, which is what CI runs:

```bash
python scripts/build_hdf5.py --check
python scripts/build_demographics.py --check
```

The fetched stores (in `fetched/`, downloaded by `fetch()` rather than shipped in the package) are published as assets of a GitHub release, named in `RELEASE` in `scripts/build_hdf5.py`. They are rebuilt only with `python scripts/build_hdf5.py --fetched`. If a store in `fetched/` changes, or a new one is added, set a new tag in `RELEASE` (e.g. `data-2027.03`) and rerun the script, so that the manifest points at a release that holds the new bytes. Data releases are never edited once published.

## Releasing

1. In the pull request, bump `__version__` and `__versiondate__` in `starsim_data/version.py` and add a section for that version to `CHANGELOG.md`, headed `## Version X.Y.Z (date)`. That section becomes the release notes.
2. Merge the pull request, then update your local `main`:
   ```bash
   git switch main
   git pull
   ```
3. Run the release script:
   ```bash
   scripts/publish_release
   ```
   It is the same whether or not the data has changed; what decides it is `RELEASE` in `scripts/build_hdf5.py`, which names the data release the fetched stores are downloaded from (see above), and the script says up front which case it is:
   - **Package only** (the usual case): no fetched store has changed, so the release named in `RELEASE` already exists. The script checks that its files are all there and creates only `v<version>`.
   - **New data and the package**: you changed a fetched store and set a new `RELEASE`, so that release doesn't exist yet. The script creates it first, with the stores in `fetched/` attached, then `v<version>`.

   Either way it first checks that you're on an up-to-date `main` with no uncommitted changes, that the stores in `fetched/` match the manifest, and that the changelog has the version's section, in a dry run, and then asks before creating anything. Each release gets its git tag on GitHub (`git fetch --tags` to get them locally). The script is a wrapper around `python scripts/publish.py <data tag> [--dry-run]`, which you can also run directly.
4. Publishing `v<version>` triggers the Publish workflow (`.github/workflows/publish.yml`), which builds the package and uploads it to PyPI. It refuses to if any fetched store can't be downloaded. Watch it under the repository's Actions tab.

PyPI accepts the upload through trusted publishing, so no token is needed. This is set up once on pypi.org, in the project's Publishing settings: owner `starsimhub`, repository `starsim_data`, workflow `publish.yml`, environment `pypi`.
