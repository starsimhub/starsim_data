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

Make the change on a branch, with a test if it fixes or adds something, and update the prose it affects: the API reference regenerates itself, but the pages in [`docs/`](docs/) don't. A new dataset or source also touches `docs/03-datasets.qmd`, `docs/06-datasources.qmd` and [`NOTICE.md`](NOTICE.md) (a test checks the licenses there against the data).

## Changing data

The `.h5` files are build artifacts: never edit them by hand. Edit the sources in [`raw_data/`](raw_data/) and rebuild with the scripts in [`scripts/`](scripts/) (its README describes each), checking the result with `--check`, which is what CI runs:

```bash
python scripts/build_hdf5.py --check
python scripts/build_demographics.py --check
```

The fetched stores (in [`fetched/`](fetched/), downloaded by `fetch()` rather than shipped in the package) are published as assets of a GitHub release, named in `RELEASE` in `scripts/build_hdf5.py`. They are rebuilt only with `python scripts/build_hdf5.py --fetched`. If a store in `fetched/` changes, or a new one is added, set a new tag in `RELEASE` (e.g. `data-2027.03`) and rerun the script, so that the manifest points at a release that holds the new bytes. Data releases are never edited once published.

## Releasing

1. In the pull request, bump `__version__` and `__versiondate__` in [`starsim_data/version.py`](starsim_data/version.py) and add a section for that version to [`CHANGELOG.md`](CHANGELOG.md). That section becomes the release notes.
2. Merge the pull request, then update your local `main`:
   ```bash
   git switch main
   git pull
   ```
3. Run the release script with the data tag, the value of `RELEASE` in `scripts/build_hdf5.py`. Do a dry run first:
   ```bash
   python scripts/pypi_release.py data-2026.10 --dry-run
   python scripts/pypi_release.py data-2026.10
   ```
   It checks that you're on an up-to-date `main` with no uncommitted changes, that the stores in `fetched/` match the manifest, and that the changelog has the version's section. Then it creates two GitHub releases, each with its git tag (`git fetch --tags` to get them locally):
   - the data release, with the stores in `fetched/` attached, unless it already exists from an earlier version, in which case it checks the files are there;
   - `v<version>`, the package release.
4. Publishing `v<version>` triggers the [Publish](.github/workflows/publish.yml) workflow, which builds the package and uploads it to PyPI. It refuses to if any fetched store can't be downloaded. Watch it under the repository's Actions tab.

PyPI accepts the upload through trusted publishing, so no token is needed. This is set up once on pypi.org, in the project's Publishing settings: owner `starsimhub`, repository `starsim_data`, workflow `publish.yml`, environment `pypi`.
