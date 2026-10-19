# tests

Tests for `starsim_data`, written in [Starsim's style](https://github.com/starsimhub/styleguide/blob/main/3_tests.md): each file runs under pytest and also as a plain script. Run from the repo root:

```bash
pip install -e ".[dev]"
pytest                      # the offline suite
pytest -m network           # also hit the UN servers (a few hundred MB of downloads)
python tests/test_load.py   # one file as a script: runs each test in turn and prints its timing
```

Most tests read the bundled `starsim_data/data/*.h5` stores, so run `python scripts/build_hdf5.py` and `python scripts/build_demographics.py` first if they are missing.

Each file ends with an `if __name__ == "__main__":` block that calls every test in the file, timed with `sc.timer()`, and keeps what each returns for inspection (e.g. in an IPython session with `%run tests/test_nodes.py`). Tests that need a pytest fixture are given a fresh `tempfile.mkdtemp()` folder or a `pytest.MonkeyPatch.context()` there. Files with `network` tests skip them as scripts unless you set `do_network = True` in the `__main__` block; those files also call `conftest.isolate_cache()` first, so a script stays out of your real cache just as pytest does. `test_plotting.py` shows its figures when run as a script.

| File | What it covers |
|---|---|
| `test_load.py` | The core API: listing, matrix shapes and axes, location matching, settings, the default contact source, fetched contact sources and their manifest, the US states, error paths |
| `test_locations.py` | Name/code/alias resolution, the "did you mean" path, `valid` scoping, subnational units, `location_info`, `parse_level`, `normalize`, and the Namibia `NA` regression |
| `test_demographics.py` | The build pipeline end to end, from synthetic WPP CSVs through `build_demographics.py` to `load` |
| `test_demographics_data.py` | Sanity checks on the real bundled demographics (plausible rates, coverage, units) |
| `test_provenance.py` | Every bundled store is attributable, licenses match `NOTICE.md`, provenance on loaded frames, revision pinning |
| `test_registry.py` | Dataset descriptors, tiers, sources, layout dispatch, and the registration hooks |
| `test_cache.py` | The download cache and `options` — no network: cache hits, sidecars, clearing, settings |
| `test_fetching.py` | `fetch()`: year parsing and file selection offline, plus `network`-marked tests that check fetched data against the bundled data |
| `test_nodes.py` | The bundled node table (schema, names, geography, populations), `distances()` and `adjacency()` — all offline |
| `test_spatial.py` | The `[spatial]` tier: boundary sources and the GADM constraint, WorldPop product selection, and `network`-marked tests of `fetch_shapes()`, `fetch_nodes()` (including our windowed raster sum against rastertoolkit's) and `choropleth()`; skips without geopandas |
| `test_plotting.py` | The summary figure, single-dataset panels, the population pyramid, the offline node plot, and the error paths |
| `test_docs.py` | The docs sources: page frontmatter and section order, cross-page links, executed cells staying offline, and great-docs' native navigation |

## Markers

- `network` — needs internet. **Deselected by default in CI.** Set `STARSIM_DATA_CACHE_DIR` to reuse the downloads between runs; otherwise each session re-fetches into a temp directory (`conftest.py` keeps tests out of your real cache either way).
- `slow` — takes more than a second or so; the life-table tests are both `network` and `slow` because they pull ~145 MB, as are the `fetch_nodes()` and choropleth tests, which download WorldPop rasters.
