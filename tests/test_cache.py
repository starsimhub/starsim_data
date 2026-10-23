"""
Test the download cache and settings. None of these touch the network.
"""

import json
import tempfile

import sciris as sc
import pytest

import starsim_data as ssd


def make_entry(root, name, url="https://example.org/x.csv", size=3):
    """ Write a cache entry and its provenance sidecar by hand """
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(b"x" * size)
    sidecar = root / (name + ssd.cache.SIDECAR_SUFFIX)
    sidecar.write_text(json.dumps(dict(url=url, filename=name, bytes=size, downloaded="2026-01-01T00:00:00+00:00")))
    return path


@sc.timer()
def test_cache_dir(tmp_path):
    """ The cache dir follows the option, is created only on request, and has a sensible default """
    sc.heading("Testing the cache directory")
    with ssd.options.context(cache_dir=str(tmp_path)):
        assert ssd.cache_dir() == tmp_path # It follows the option
        assert ssd.cache_dir("wpp") == tmp_path / "wpp" # Subdirectories go under it

    target = tmp_path / "does_not_exist_yet"
    with ssd.options.context(cache_dir=str(target)):
        assert not ssd.cache_dir().exists() # Asking where it is must be side-effect free
        assert ssd.cache_dir(create=True).is_dir() # Unless asked to create it

    with ssd.options.context(cache_dir=None):
        path = ssd.cache_dir()
    assert path.is_absolute() # The platform default is absolute
    assert path.name in ("starsim_data", "Cache") # And named for the package, or the platform's cache folder
    return path


@sc.timer()
def test_env(monkeypatch):
    """ STARSIM_DATA_CACHE_DIR is read at import; reconstructing options picks it up """
    sc.heading("Testing the cache environment variable")
    monkeypatch.setenv("STARSIM_DATA_CACHE_DIR", "/tmp/some_cache")
    _, defaults = ssd.options.get_orig_options()
    assert defaults.cache_dir == "/tmp/some_cache" # The environment sets the default
    return defaults


@sc.timer()
def test_cache_hit(tmp_path):
    """ A cache hit must not touch the network -- the URL here is deliberately bogus """
    sc.heading("Testing a cache hit")
    with ssd.options.context(cache_dir=str(tmp_path), verbose=False):
        (tmp_path / "wpp").mkdir()
        target = tmp_path / "wpp" / "already_here.csv.gz"
        target.write_bytes(b"pretend this is gzip")
        got = ssd.cache.cached_download("https://no.such.host/already_here.csv.gz", filename="already_here.csv.gz", subdir="wpp")
    assert got == target # The cached file is returned
    assert got.read_bytes() == b"pretend this is gzip" # Untouched
    return got


@sc.timer()
def test_cache_info(tmp_path):
    """ cache_info() lists the entries, and cache_provenance() reads their sidecars """
    sc.heading("Testing cache_info and cache_provenance")
    with ssd.options.context(cache_dir=str(tmp_path), verbose=False):
        empty = ssd.cache_info()
        assert len(empty) == 0 # Nothing cached yet
        assert "file" in empty.columns # Still a usable frame

        a = make_entry(tmp_path / "wpp", "a.csv", url="https://example.org/a.csv")
        make_entry(tmp_path / "wpp", "b.csv", url="https://example.org/b.csv")
        info = ssd.cache_info()
        assert list(info.file) == ["wpp/a.csv", "wpp/b.csv"] # Sidecars are not listed
        assert list(info.url) == ["https://example.org/a.csv", "https://example.org/b.csv"] # Each with its URL
        assert info.bytes.sum() == 6 # And its size

        assert ssd.cache_provenance(a).url == "https://example.org/a.csv" # The sidecar round-trips
        orphan = tmp_path / "orphan.csv"
        orphan.write_bytes(b"x")
        assert ssd.cache_provenance(orphan) is None # No sidecar, no provenance
    return info


@sc.timer()
def test_clear_cache(tmp_path):
    """ clear_cache() removes what matches, with its sidecar, and leaves the rest """
    sc.heading("Testing clear_cache")
    some = tmp_path / "some"
    with ssd.options.context(cache_dir=str(some), verbose=False):
        make_entry(some / "wpp", "a.csv")
        make_entry(some / "other", "b.csv")
        removed = ssd.clear_cache("wpp/*")
        assert removed == ["wpp/a.csv"] # Only what matches the pattern
        assert not (some / "wpp" / "a.csv").exists() # The file is gone
        assert not (some / "wpp" / ("a.csv" + ssd.cache.SIDECAR_SUFFIX)).exists() # And its sidecar
        assert (some / "other" / "b.csv").exists() # The rest is untouched

    everything = tmp_path / "everything"
    with ssd.options.context(cache_dir=str(everything), verbose=False):
        make_entry(everything / "wpp", "a.csv")
        make_entry(everything / "other", "b.csv")
        assert sorted(ssd.clear_cache()) == ["other/b.csv", "wpp/a.csv"] # No pattern removes everything
        assert not everything.exists() # Including the directory

    with ssd.options.context(cache_dir=str(tmp_path / "nope"), verbose=False):
        assert ssd.clear_cache() == [] # A missing directory is a no-op
    return removed


@sc.timer()
def test_options():
    """ Options can be set, reset, used as a context, and described """
    sc.heading("Testing options")
    cache_dir = ssd.options.cache_dir # reset() would undo the session's isolation
    ssd.options(verbose=False)
    assert ssd.options.verbose is False # Set
    ssd.options.reset()
    assert ssd.options.verbose is True # Reset
    ssd.options.cache_dir = cache_dir

    before = ssd.options.verbose
    with ssd.options.context(verbose=not before):
        assert ssd.options.verbose is (not before) # Changed inside the context
    assert ssd.options.verbose is before # Restored after it

    with pytest.raises(KeyError, match="unknown option"):
        ssd.options(no_such_option=1)

    text = ssd.options.help(output=True)
    assert "cache_dir" in text # The help describes each option
    assert "verbose" in text
    return text


if __name__ == "__main__":
    T = sc.timer()

    path  = test_cache_dir(sc.path(tempfile.mkdtemp()))
    with pytest.MonkeyPatch.context() as monkeypatch:
        env = test_env(monkeypatch)
    hit   = test_cache_hit(sc.path(tempfile.mkdtemp()))
    info  = test_cache_info(sc.path(tempfile.mkdtemp()))
    clear = test_clear_cache(sc.path(tempfile.mkdtemp()))
    text  = test_options()

    T.toc()
