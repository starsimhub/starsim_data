"""Tests for the download cache and settings. None of these touch the network."""

import json

import pytest

import starsim_data as ssd


@pytest.fixture
def tmp_cache(tmp_path):
    """Point the cache at a temp dir for the duration of one test."""
    with ssd.options.context(cache_dir=str(tmp_path), verbose=False):
        yield tmp_path


def test_cache_dir_follows_the_option(tmp_cache):
    assert ssd.cache_dir() == tmp_cache
    assert ssd.cache_dir("wpp") == tmp_cache / "wpp"


def test_cache_dir_does_not_create_by_default(tmp_path):
    target = tmp_path / "does_not_exist_yet"
    with ssd.options.context(cache_dir=str(target)):
        assert not ssd.cache_dir().exists()      # asking where it is must be side-effect free
        assert ssd.cache_dir(create=True).is_dir()


def test_default_cache_dir_is_platform_appropriate():
    with ssd.options.context(cache_dir=None):
        path = ssd.cache_dir()
    assert path.is_absolute()
    assert path.name in ("starsim_data", "Cache")


def test_env_var_is_read(monkeypatch):
    """STARSIM_DATA_CACHE_DIR is read at import; reconstructing options picks it up."""
    monkeypatch.setenv("STARSIM_DATA_CACHE_DIR", "/tmp/some_cache")
    _, defaults = ssd.options.get_orig_options()
    assert defaults.cache_dir == "/tmp/some_cache"


def test_a_cached_file_is_returned_without_downloading(tmp_cache):
    """A cache hit must not touch the network -- the URL here is deliberately bogus."""
    (tmp_cache / "wpp").mkdir()
    target = tmp_cache / "wpp" / "already_here.csv.gz"
    target.write_bytes(b"pretend this is gzip")
    got = ssd.cache.cached_download("https://no.such.host/already_here.csv.gz",
                                    filename="already_here.csv.gz", subdir="wpp")
    assert got == target
    assert got.read_bytes() == b"pretend this is gzip"


def _fake_entry(root, name, url="https://example.org/x.csv", size=3):
    """Write a cache entry and its provenance sidecar by hand."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(b"x" * size)
    sidecar = root / (name + ssd.cache.SIDECAR_SUFFIX)
    sidecar.write_text(json.dumps(dict(url=url, filename=name, bytes=size,
                                       downloaded="2026-01-01T00:00:00+00:00")))
    return path


def test_cache_info_lists_entries(tmp_cache):
    _fake_entry(tmp_cache / "wpp", "a.csv", url="https://example.org/a.csv")
    _fake_entry(tmp_cache / "wpp", "b.csv", url="https://example.org/b.csv")
    info = ssd.cache_info()
    assert list(info.file) == ["wpp/a.csv", "wpp/b.csv"]      # sidecars are not listed
    assert list(info.url) == ["https://example.org/a.csv", "https://example.org/b.csv"]
    assert info.bytes.sum() == 6


def test_cache_info_is_empty_when_nothing_is_cached(tmp_cache):
    info = ssd.cache_info()
    assert len(info) == 0
    assert "file" in info.columns          # still a usable frame


def test_cache_provenance_round_trip(tmp_cache):
    path = _fake_entry(tmp_cache / "wpp", "a.csv")
    assert ssd.cache_provenance(path).url == "https://example.org/x.csv"


def test_cache_provenance_is_none_when_absent(tmp_cache):
    path = tmp_cache / "orphan.csv"
    path.write_bytes(b"x")
    assert ssd.cache_provenance(path) is None


def test_clear_cache_by_pattern(tmp_cache):
    _fake_entry(tmp_cache / "wpp", "a.csv")
    _fake_entry(tmp_cache / "other", "b.csv")
    removed = ssd.clear_cache("wpp/*")
    assert removed == ["wpp/a.csv"]
    assert not (tmp_cache / "wpp" / "a.csv").exists()
    assert not (tmp_cache / "wpp" / ("a.csv" + ssd.cache.SIDECAR_SUFFIX)).exists()
    assert (tmp_cache / "other" / "b.csv").exists()          # untouched


def test_clear_cache_removes_everything(tmp_cache):
    _fake_entry(tmp_cache / "wpp", "a.csv")
    _fake_entry(tmp_cache / "other", "b.csv")
    assert sorted(ssd.clear_cache()) == ["other/b.csv", "wpp/a.csv"]
    assert not tmp_cache.exists()


def test_clear_cache_on_a_missing_directory_is_a_no_op(tmp_path):
    with ssd.options.context(cache_dir=str(tmp_path / "nope"), verbose=False):
        assert ssd.clear_cache() == []


# --- Settings ---------------------------------------------------------------------- #

def test_options_set_and_reset():
    cache_dir = ssd.options.cache_dir       # reset() would undo the session's isolation
    ssd.options(verbose=False)
    assert ssd.options.verbose is False
    ssd.options.reset()
    assert ssd.options.verbose is True
    ssd.options.cache_dir = cache_dir


def test_options_context_restores():
    before = ssd.options.verbose
    with ssd.options.context(verbose=not before):
        assert ssd.options.verbose is (not before)
    assert ssd.options.verbose is before


def test_unknown_option_raises():
    with pytest.raises(KeyError, match="unknown option"):
        ssd.options(no_such_option=1)


def test_options_help_returns_text():
    text = ssd.options.help(output=True)
    assert "cache_dir" in text and "verbose" in text
