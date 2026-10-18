"""
Package-level settings.

Everything here is optional: the bundled data (tier 0) needs no configuration at all.
These settings exist for the parts that touch the filesystem or the network -- the
download cache used by `fetch()`.

Settings are read from the environment at import time but *acted on* lazily, so nothing
here creates a directory, opens a file or emits a warning merely because the package was
imported. The cache directory is not created until something is actually cached.

```python
import starsim_data as ssd
ssd.options.cache_dir = '/fast/scratch/wpp'   # or set STARSIM_DATA_CACHE_DIR
ssd.options(verbose=False)                     # quieten downloads
with ssd.options.context(cache_dir='/tmp/x'):  # temporarily
    ssd.fetch('kenya', which='deaths')
```
"""

import contextlib
import sciris as sc

__all__ = ['options']


class Options(sc.objdict):
    """Settings for `starsim_data`; the instance to use is `starsim_data.options`.

    Follows Starsim's `ss.options` conventions: an `objdict` whose entries can be set by
    attribute, by call, or from an environment variable.

    Example:
        >>> import starsim_data as ssd
        >>> ssd.options(verbose=False)
        >>> ssd.options.reset()
    """

    def __init__(self):
        super().__init__()
        optdesc, options = self.get_orig_options()
        self.update(options)
        self.setattribute('optdesc', optdesc) # Set the description as an attribute, not a dict entry
        self.setattribute('orig_options', sc.dcp(options))
        return

    @staticmethod
    def get_orig_options():
        """Return `(descriptions, defaults)`; use `options.reset()` rather than calling this."""
        optdesc = sc.objdict()
        options = sc.objdict()

        optdesc.cache_dir = 'Where downloaded (non-bundled) data is cached. None means a platform-appropriate default; see cache_dir().'
        options.cache_dir = sc.parse_env('STARSIM_DATA_CACHE_DIR', None, None) # which=None so an unset variable stays None rather than becoming an empty string

        optdesc.verbose = 'Whether to report progress while downloading.'
        options.verbose = sc.parse_env('STARSIM_DATA_VERBOSE', True, bool)

        return optdesc, options

    def __call__(self, *args, **kwargs):
        """Allow `options(verbose=False)` as shorthand for `options.set(verbose=False)`."""
        return self.set(*args, **kwargs)

    def set(self, key=None, value=None, **kwargs):
        """Set one or more options, e.g. `options.set('verbose', False)` or `options.set(verbose=False)`."""
        if key is not None:
            kwargs = sc.mergedicts(kwargs, {key: value})
        for name, val in kwargs.items():
            if name not in self.orig_options:
                raise KeyError(f'unknown option {name!r}; valid options are {sc.strjoin(self.orig_options.keys())}')
            if val == 'default':
                val = self.orig_options[name]
            self[name] = val
        return self

    def reset(self):
        """Restore all options to their defaults."""
        self.update(sc.dcp(self.orig_options))
        return self

    @contextlib.contextmanager
    def context(self, **kwargs):
        """Set options temporarily, restoring the previous values on exit.

        Example:
            >>> import starsim_data as ssd
            >>> with ssd.options.context(verbose=False):
            ...     pass
        """
        previous = {key: self[key] for key in kwargs}
        self.set(**kwargs)
        try:
            yield self
        finally:
            self.set(**previous)

    def help(self, output=False):
        """Print (or return) each option with its description and current value."""
        lines = [f'{key:>12s} = {self[key]!r:<28} # {self.optdesc[key]}' for key in self.orig_options]
        text = sc.newlinejoin(lines)
        if output:
            return text
        print(text)
        return


options = Options()
