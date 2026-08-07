# tests

Pytest suite for `starsim_data`. Run from the repo root:

```bash
pip install -e ".[dev]"
pytest                      # the offline suite
pytest -m network           # also hit the UN servers (a few hundred MB of downloads)
```

Most tests read the bundled `starsim_data/data/*.h5` stores, so run `python scripts/build_hdf5.py` and `python scripts/build_demographics.py` first if they are missing.

| File | What it covers |
|---|---|
| `test_load.py` | The core API: matrix shapes and dtypes, location matching, per-setting loading, error paths |
| `test_locations.py` | Name/code/alias resolution, the "did you mean" path, `parse_level`, and the Namibia `NA` regression |
| `test_demographics.py` | The build pipeline end to end, from synthetic WPP CSVs through `build_demographics.py` to `load` |
| `test_demographics_data.py` | Sanity checks on the real bundled demographics (plausible rates, coverage, units) |
| `test_provenance.py` | Every bundled store is attributable, licenses match `NOTICE.md`, revision pinning |
| `test_registry.py` | Dataset descriptors, tiers, layout dispatch, and the registration hooks |
| `test_cache.py` | The download cache and `options` — no network: cache hits, sidecars, clearing, settings |
| `test_fetching.py` | `fetch()`: year parsing and file selection offline, plus `network`-marked tests that check fetched data against the bundled data |
| `test_plotting.py` | Each plotter draws, the summary skips absent datasets, and the error paths |

## Markers

- `network` — needs internet. **Deselected by default in CI.** Set `STARSIM_DATA_CACHE_DIR` to reuse the downloads between runs; otherwise each session re-fetches into a temp directory (`conftest.py` keeps tests out of your real cache either way).
- `slow` — takes more than a second or so; the life-table tests are both `network` and `slow` because they pull ~145 MB.
