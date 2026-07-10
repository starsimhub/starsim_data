# tests

Pytest suite for `starsim_data`. Run from the repo root:

```bash
pip install -e ".[dev]"
pytest
```

`test_load.py` exercises the public API (`load`, `list_datasets`, `list_locations`): matrix shapes and dtype, case/space-insensitive location matching, per-setting loading, and the error paths. The tests read the bundled `starsim_data/data/*.h5` stores, so run `python scripts/build_hdf5.py` first if they are missing.
