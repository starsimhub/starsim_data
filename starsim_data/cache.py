"""
Download cache for data that is too big to bundle.

Tier-0 data ships inside the wheel and `load()` never touches the network. Anything
larger -- the UN WPP bulk files behind `fetch()`, and later the spatial sources -- is
downloaded once into a local cache and reused from then on.

Every cached file gets a provenance sidecar (`<file>.provenance.json`) recording the URL
it came from, when it was downloaded, its size and its SHA-256. That is `laser-init`'s
idea, and it is the right one for fetched files: unlike bundled data, where provenance
is written into the HDF5 itself, a cache entry is an ordinary file on disk and a sidecar
is the only place the lineage can live.

```python
import starsim_data as ssd
ssd.cache_dir()      # where things are cached
ssd.cache_info()     # what is cached, from where, and when it was fetched
ssd.clear_cache()    # delete it all
```
"""

import hashlib
import json
import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

import sciris as sc
import starsim_data as ssd

__all__ = ["cache_dir", "cache_info", "clear_cache"]

SIDECAR_SUFFIX = ".provenance.json"

# Read in chunks rather than all at once: cached WPP files run to a few hundred MB.
HASH_CHUNK = 1 << 20


def _default_cache_dir():
    """Return the platform-appropriate cache location, without creating it."""
    system = platform.system()
    if system == "Windows":
        root = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(root) / "starsim_data" / "Cache"
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "starsim_data"
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "starsim_data"


def cache_dir(subdir=None, create=False):
    """Return the directory where downloaded data is cached.

    Resolved at call time from `ssd.options.cache_dir`, falling back to a platform default
    (`~/.cache/starsim_data` on Linux, `~/Library/Caches/starsim_data` on macOS,
    `%LOCALAPPDATA%\\starsim_data\\Cache` on Windows). Nothing is created unless
    `create=True`, so merely asking where the cache is has no side effects.

    Args:
        subdir (str): optional subdirectory within the cache, e.g. `'wpp'`.
        create (bool): whether to create the directory if it does not exist.

    Returns:
        pathlib.Path: the cache directory.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.cache_dir().name
        'starsim_data'
    """
    path = Path(ssd.options.cache_dir).expanduser() if ssd.options.cache_dir else _default_cache_dir()
    if subdir:
        path = path / subdir
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sidecar(path, url):
    """Record where a cached file came from, alongside it."""
    facts = dict(url=url,
                 filename=path.name,
                 downloaded=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 bytes=path.stat().st_size,
                 sha256=_sha256(path),
                 package_version=ssd.__version__)
    Path(str(path) + SIDECAR_SUFFIX).write_text(json.dumps(facts, indent=2), encoding="utf-8")
    return facts


def cached_download(url, filename=None, subdir=None, refresh=False, verbose=None):
    """Download `url` into the cache, or return the existing path if already cached.

    Args:
        url (str): the URL to fetch.
        filename (str): name to save as (default: the last path component of the URL).
        subdir (str): subdirectory of the cache to put it in, e.g. `'wpp'`.
        refresh (bool): re-download even if a cached copy exists.
        verbose (bool): report progress (default: `ssd.options.verbose`).

    Returns:
        pathlib.Path: the path to the cached file.
    """
    verbose = ssd.options.verbose if verbose is None else verbose
    filename = filename or url.rstrip("/").split("/")[-1]
    path = cache_dir(subdir, create=True) / filename

    if path.is_file() and not refresh:
        if verbose:
            print(f"Using cached {path} ({sc.humanize_bytes(path.stat().st_size)})")
        return path

    if verbose:
        print(f"Downloading {url}\n  -> {path}")
    # convert=False keeps the response as bytes; the WPP files are gzipped CSVs and
    # sciris would otherwise try to decode them as text.
    sc.download(url, filename=str(path), convert=False, verbose=verbose)
    _write_sidecar(path, url)
    return path


def cache_provenance(path):
    """Return the recorded provenance for a cached file, or None if there is none."""
    sidecar = Path(str(path) + SIDECAR_SUFFIX)
    if not sidecar.is_file():
        return None
    return sc.objdict(json.loads(sidecar.read_text(encoding="utf-8")))


def _cached_files():
    """Yield every cached data file (i.e. excluding the provenance sidecars)."""
    root = cache_dir()
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.endswith(SIDECAR_SUFFIX):
            yield path


def cache_info():
    """Return a dataframe of what is currently cached: file, size, source URL and date.

    Returns:
        sciris.dataframe: with columns `[file, size, bytes, url, downloaded]`, empty if
        nothing is cached.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.cache_info()  # doctest: +SKIP
    """
    root = cache_dir()
    rows = []
    for path in _cached_files():
        prov = cache_provenance(path) or {}
        size = path.stat().st_size
        rows.append(dict(file=str(path.relative_to(root)),
                         size=sc.humanize_bytes(size),
                         bytes=size,
                         url=prov.get("url", ""),
                         downloaded=prov.get("downloaded", "")))
    return sc.dataframe(rows, columns=["file", "size", "bytes", "url", "downloaded"])


def clear_cache(pattern=None, verbose=None):
    """Delete cached downloads. Bundled data is never touched.

    Args:
        pattern (str): a glob matched against each cached file's path relative to the
            cache root, e.g. `'wpp/*'`. If None, the whole cache is removed.
        verbose (bool): report what was deleted (default: `ssd.options.verbose`).

    Returns:
        list: the paths that were deleted.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.clear_cache('wpp/*')  # doctest: +SKIP
    """
    verbose = ssd.options.verbose if verbose is None else verbose
    root = cache_dir()
    if not root.is_dir():
        return []

    if pattern is None:
        removed = [str(p.relative_to(root)) for p in _cached_files()]
        shutil.rmtree(root)
    else:
        removed = []
        for path in _cached_files():
            if path.relative_to(root).match(pattern):
                Path(str(path) + SIDECAR_SUFFIX).unlink(missing_ok=True)
                path.unlink()
                removed.append(str(path.relative_to(root)))

    if verbose:
        print(f"Removed {len(removed)} cached file(s) from {root}")
    return removed
