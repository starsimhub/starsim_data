"""
Validation plots.

These exist to catch the errors that are invisible in a table and obvious in a picture:
the wrong country, the wrong units, a mortality curve that does not bend the way a
mortality curve bends. Plotting the data before it goes into a simulation is the cheapest
check there is.

```python
import starsim_data as ssd
ssd.plot('kenya')                            # a 4-panel summary: pyramid, rates, mx, matrix
ssd.plot('kenya', which='population')        # just the age pyramid
ssd.plot('kenya', which='prem2017')          # just the contact matrix
```

One plotter per layout, looked up in `PLOTTERS`; a new layout can add itself by assigning
into that dict, in the same spirit as `ssd.registry.LAYOUTS`. `matplotlib` arrives with
sciris (which imports `pyplot` itself) and is a direct Starsim dependency, so this costs
nothing at import time and needs no optional extra.
"""

import datetime

import matplotlib.pyplot as plt
import numpy as np
import sciris as sc
import starsim_data as ssd

__all__ = ["plot"]

# The panels in the default summary figure, in order; those absent for a location are
# skipped rather than left blank.
SUMMARY = ("population", "births", "deaths", "prem2017")

SEX_COLORS = {"Female": "#c2185b", "Male": "#1976d2"}


def _default_year(years):
    """Return the most recent year that is not a projection, else the earliest available."""
    today = datetime.date.today().year
    past = [y for y in years if y <= today]
    return max(past) if past else min(years)


def _plot_population(ax, df, location, year=None):
    """Age pyramid: females left, males right, for a single year."""
    year = _default_year(sorted(df.Time.unique())) if year is None else int(year)
    frame = df[df.Time == year]
    if frame.empty:
        raise ValueError(f"no population data for {year}; available: {sorted(df.Time.unique())}")
    ages = np.sort(frame.AgeGrp.unique())
    height = np.diff(ages).min() * 0.9 if len(ages) > 1 else 1
    for sex, sign in (("Female", -1), ("Male", 1)):
        values = frame[frame.Sex == sex].set_index("AgeGrp").Value.reindex(ages).to_numpy()
        ax.barh(ages, sign * values / 1e6, height=height, color=SEX_COLORS[sex], label=sex)
    ax.axvline(0, color="k", lw=0.8)
    # Both wings are populations, so label the axis with magnitudes rather than signs.
    ax.xaxis.set_major_formatter(lambda x, _: f"{abs(x):g}")
    ax.set_xlabel("Population (millions)")
    ax.set_ylabel("Age")
    ax.set_title(f"{location}, {year}")
    ax.legend(frameon=False)


def _plot_crude(ax, df, location, year=None):  # pylint: disable=unused-argument
    """A national rate against time, e.g. the crude birth rate."""
    value_col = [c for c in df.columns if c != "Time"][0]
    ax.plot(df.Time, df[value_col], marker="o", ms=3, color="#00796b")
    ax.set_xlabel("Year")
    ax.set_ylabel(value_col)
    ax.set_title(f"{location}: {value_col}")
    ax.axhline(0, color="k", lw=0.8, zorder=0)


def _plot_mortality(ax, df, location, year=None):
    """Mortality rate against age, by sex, on a log scale -- the shape is the check."""
    year = _default_year(sorted(df.Time.unique())) if year is None else int(year)
    frame = df[df.Time == year]
    if frame.empty:
        raise ValueError(f"no mortality data for {year}; available: {sorted(df.Time.unique())}")
    for sex, color in SEX_COLORS.items():
        rows = frame[frame.Sex == sex].sort_values("AgeGrpStart")
        ax.semilogy(rows.AgeGrpStart, rows.mx, color=color, label=sex)
    ax.set_xlabel("Age")
    ax.set_ylabel("Mortality rate m(x)")
    ax.set_title(f"{location}, {year}")
    ax.legend(frameon=False)


def _plot_matrix(ax, df, location, year=None):  # pylint: disable=unused-argument
    """Contact matrix heatmap, axes labelled by the start age of each bin."""
    ages = np.asarray(df.index)
    img = ax.imshow(df.to_numpy(), origin="lower", cmap="viridis", aspect="equal",
                    extent=(ages[0], ages[-1], ages[0], ages[-1]))
    ax.set_xlabel("Age of contact")
    ax.set_ylabel("Age of participant")
    ax.set_title(location)
    ax.get_figure().colorbar(img, ax=ax, label="Contacts per day")


# Layout -> plotter. Assign into this to support a layout registered with
# `ssd.registry.register_layout`.
PLOTTERS = {
    "population": _plot_population,
    "crude": _plot_crude,
    "mortality": _plot_mortality,
    "matrix": _plot_matrix,
}


def _panels(location, which):
    """Return the `(dataset, dataframe)` pairs to draw.

    A summary figure skips datasets that are missing for this location -- not every
    country has every contact source. An explicit `which` does not: if you asked for it
    and it is not there, that is an error, not a blank panel.
    """
    summary = which is None
    # Resolve up front so an unknown *location* fails with the usual suggestions, rather
    # than being mistaken for a location that is merely absent from every dataset.
    location = ssd.resolve(location)
    out = []
    for name in (SUMMARY if summary else sc.tolist(which)):
        ds = ssd.registry.datasets().get(name)
        if ds is None or ds.tier > 0 or ds.layout not in PLOTTERS:
            if summary:
                continue
            plottable = sorted(n for n, d in ssd.registry.datasets().items()
                               if d.tier == 0 and d.layout in PLOTTERS)
            raise ValueError(f"cannot plot {name!r}; plottable datasets are {plottable}")
        try:
            out.append((ds, ssd.load(location, which=name)))
        except KeyError:            # this location is absent from that dataset
            if not summary:
                raise
    if not out:
        raise ValueError(f"no plottable data for {location!r}")
    return out


def plot(location, which=None, year=None, fig_kw=None):
    """
    Plot data for a location, as a quick check before it goes into a model.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        which (str/list): dataset(s) to plot. None (default) draws a summary figure --
            age pyramid, crude birth rate, mortality curve and contact matrix -- skipping
            any the location lacks.
        year (int): the year to show for the single-year panels (age pyramid, mortality
            curve). Defaults to the most recent year that is not a projection.
        fig_kw (dict): passed to `plt.subplots`, e.g. `dict(figsize=(12, 8))`.

    Returns:
        matplotlib.figure.Figure: the figure, so it can be saved or further adjusted.

    Example:
        >>> import starsim_data as ssd
        >>> fig = ssd.plot('kenya')                       # doctest: +SKIP
        >>> fig = ssd.plot('kenya', which='population')   # doctest: +SKIP
    """
    panels = _panels(location, which)
    ncols = 1 if len(panels) == 1 else 2
    nrows = int(np.ceil(len(panels) / ncols))
    fig_kw = sc.mergedicts(dict(figsize=(6 * ncols, 4.5 * nrows), layout="constrained"), fig_kw)
    fig, axes = plt.subplots(nrows, ncols, **fig_kw)
    flat = np.atleast_1d(np.asarray(axes)).ravel()

    for ax, (ds, df) in zip(flat, panels):
        PLOTTERS[ds.layout](ax, df, df.attrs.get("location", location), year=year)
        if which is None:
            ax.set_title(f"{ds.name}: {ax.get_title()}", fontsize=10)
    for ax in flat[len(panels):]:
        ax.set_visible(False)
    return fig
