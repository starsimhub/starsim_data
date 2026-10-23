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
ssd.plot('kenya', which='nodes', level=1)    # where the admin units are (centroids)
ssd.choropleth('kenya', level=1)             # ... and filled polygons, with [spatial]
```

One plotter per layout, looked up in `PLOTTERS`; a new layout can add itself by assigning
into that dict, in the same spirit as `ssd.registry.LAYOUTS`. `matplotlib` arrives with
sciris (which imports `pyplot` itself) and is a direct Starsim dependency, so this costs
nothing at import time and needs no optional extra.
"""

import numpy as np
import sciris as sc
import matplotlib.pyplot as plt
import starsim_data as ssd

__all__ = ['plot', 'choropleth']

# The panels in the default summary figure, in order; those absent for a location are
# skipped rather than left blank.
SUMMARY = ('population', 'births', 'deaths', 'prem')

SEX_COLORS = {'Female': '#c2185b', 'Male': '#1976d2'}


def _default_year(years):
    """Return the most recent year that is not a projection, else the earliest available."""
    this_year = sc.now().year
    past = [y for y in years if y <= this_year]
    return max(past) if past else min(years)


def _pick_year(df, year, what):
    """The rows of `df` for `year` (default: the most recent year that is not a projection)."""
    years = sorted(df.Time.unique())
    year = _default_year(years) if year is None else int(year)
    frame = df[df.Time == year]
    if frame.empty:
        raise ValueError(f'no {what} data for {year}; available: {years}')
    return frame, year


def _abs_label(x, pos):
    """Label an axis tick by its magnitude, e.g. for the two wings of an age pyramid."""
    return f'{abs(x):g}'


def _plot_population(ax, df, location, year=None):
    """Age pyramid: females left, males right, for a single year."""
    frame, year = _pick_year(df, year, 'population')
    ages = np.sort(frame.AgeGrp.unique())
    height = np.diff(ages).min() * 0.9 if len(ages) > 1 else 1
    for sex, sign in [('Female', -1), ('Male', 1)]:
        values = frame[frame.Sex == sex].set_index('AgeGrp').Value.reindex(ages).to_numpy()
        ax.barh(ages, sign * values / 1e6, height=height, color=SEX_COLORS[sex], label=sex)
    ax.axvline(0, color='k', lw=0.8)
    ax.xaxis.set_major_formatter(_abs_label) # Both wings are populations, so label the axis with magnitudes rather than signs
    ax.set_xlabel('Population (millions)')
    ax.set_ylabel('Age')
    ax.set_title(f'{location}, {year}')
    ax.legend(frameon=False)
    return


def _plot_crude(ax, df, location, year=None):
    """A national rate against time, e.g. the crude birth rate."""
    value_col = [c for c in df.columns if c != 'Time'][0]
    ax.plot(df.Time, df[value_col], marker='o', ms=3, color='#00796b')
    ax.set_xlabel('Year')
    ax.set_ylabel(value_col)
    ax.set_title(f'{location}: {value_col}')
    ax.axhline(0, color='k', lw=0.8, zorder=0)
    return


def _plot_mortality(ax, df, location, year=None):
    """Mortality rate against age, by sex, on a log scale -- the shape is the check."""
    frame, year = _pick_year(df, year, 'mortality')
    for sex, color in SEX_COLORS.items():
        rows = frame[frame.Sex == sex].sort_values('AgeGrpStart')
        ax.semilogy(rows.AgeGrpStart, rows.mx, color=color, label=sex)
    ax.set_xlabel('Age')
    ax.set_ylabel('Mortality rate m(x)')
    ax.set_title(f'{location}, {year}')
    ax.legend(frameon=False)
    return


def _plot_nodes(ax, df, location, year=None):
    """Where the administrative units are: centroids, sized by area.

    The map without the map -- enough to see that the units are in the right country and
    the right shape of cluster, with no geospatial dependency. `choropleth()` draws the
    actual polygons.
    """
    sizes = 20 + 180 * np.sqrt(df.area_km2 / df.area_km2.max())
    filled = df.population.notna()
    if filled.any() and filled.all():
        colors, label = df.population, 'Population'
    else:
        colors, label = df.area_km2, 'Area (km$^2$)'
    points = ax.scatter(df.lon, df.lat, s=sizes, c=colors, cmap='viridis', edgecolor='k', linewidth=0.4, alpha=0.85)
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.set_aspect('equal', adjustable='datalim')
    ax.set_title(f'{location}: {len(df)} node(s), level {df.level.iloc[0]}')
    ax.get_figure().colorbar(points, ax=ax, label=label)
    return


def _plot_matrix(ax, df, location, year=None):
    """Contact matrix heatmap, axes labeled by the start age of each bin."""
    ages = np.asarray(df.index)
    extent = (ages[0], ages[-1], ages[0], ages[-1])
    img = ax.imshow(df.to_numpy(), origin='lower', cmap='viridis', aspect='equal', extent=extent)
    ax.set_xlabel('Age of contact')
    ax.set_ylabel('Age of participant')
    ax.set_title(location)
    ax.get_figure().colorbar(img, ax=ax, label='Contacts per day')
    return


# Layout -> plotter. Assign into this to support a layout registered with
# `ssd.registry.register_layout`.
PLOTTERS = {
    'population': _plot_population,
    'crude':      _plot_crude,
    'mortality':  _plot_mortality,
    'matrix':     _plot_matrix,
    'nodes':      _plot_nodes,
}


def _panels(location, which, level=None):
    """Return the `(dataset, dataframe)` pairs to draw.

    A summary figure skips datasets that are missing for this location -- not every
    country has every contact source. An explicit `which` does not: if you asked for it
    and it is not there, that is an error, not a blank panel.
    """
    summary = which is None
    names = SUMMARY if summary else sc.tolist(which)
    known = ssd.registry.datasets()
    plottable = sorted(n for n, d in known.items() if (d.tier == 0) and (d.layout in PLOTTERS))

    # Resolve up front so an unknown *location* fails with the usual suggestions, rather
    # than being mistaken for a location that is merely absent from every dataset
    location = ssd.resolve(location)
    out = []
    for name in names:
        if name not in plottable:
            if summary:
                continue
            raise ValueError(f'cannot plot {name!r}; plottable datasets are {plottable}')
        ds = known[name]
        kwargs = dict(level=level) if ds.layout == 'nodes' else {}
        try:
            df = ssd.load(location, which=name, **kwargs)
        except KeyError: # This location is absent from that dataset
            if summary:
                continue
            raise
        out.append((ds, df))
    if not out:
        raise ValueError(f'no plottable data for {location!r}')
    return out


def plot(location, which=None, year=None, level=1, fig_kw=None):
    """
    Plot data for a location, as a quick check before it goes into a model.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        which (str/list): dataset(s) to plot. None (default) draws a summary figure --
            age pyramid, crude birth rate, mortality curve and contact matrix -- skipping
            any the location lacks.
        year (int): the year to show for the single-year panels (age pyramid, mortality
            curve). Defaults to the most recent year that is not a projection.
        level (int/str): the administrative level, for `which='nodes'` only.
        fig_kw (dict): passed to `plt.subplots`, e.g. `dict(figsize=(12, 8))`.

    Returns:
        matplotlib.figure.Figure: the figure, so it can be saved or further adjusted.

    Example:
        >>> import starsim_data as ssd
        >>> fig = ssd.plot('kenya')                       # doctest: +SKIP
        >>> fig = ssd.plot('kenya', which='population')   # doctest: +SKIP
    """
    panels = _panels(location, which, level=level)
    ncols = 1 if len(panels) == 1 else 2
    nrows = int(np.ceil(len(panels) / ncols))
    fig_kw = sc.mergedicts(dict(figsize=(6*ncols, 4.5*nrows), layout='constrained'), fig_kw)
    fig, axes = plt.subplots(nrows, ncols, **fig_kw)
    axes = np.atleast_1d(axes).ravel()

    for ax, (ds, df) in zip(axes, panels):
        plotter = PLOTTERS[ds.layout]
        plotter(ax, df, df.attrs.get('location', location), year=year)
        if which is None:
            ax.set_title(f'{ds.name}: {ax.get_title()}', fontsize=10)
    for ax in axes[len(panels):]:
        ax.set_visible(False) # Hide any spare panels
    return fig


def choropleth(location, level=1, value='population', shapes=None, ax=None, cmap='viridis',
               fig_kw=None, **kwargs):
    """
    Draw a filled map of an administrative value -- the geometry version of `plot(which='nodes')`.

    Requires the `[spatial]` extra, because it needs real polygons. If you only want to
    see roughly where the units are, `plot(location, which='nodes')` does that with the
    bundled centroids and no extra dependencies.

    Args:
        location (str): location name, ISO-2/ISO-3 code, official name or alias.
        level (int/str): administrative level to draw (default 1).
        value (str): the column to color by. `'population'` (default) fetches it from
            WorldPop; any other name must already be a column of `shapes`.
        shapes (GeoDataFrame): draw these instead of fetching, e.g. a frame you have
            already merged your own values onto.
        ax (matplotlib.axes.Axes): draw into this axes rather than making a figure.
        cmap (str): the colormap.
        fig_kw (dict): passed to `plt.subplots` when creating a figure.
        **kwargs: passed to `GeoDataFrame.plot`, e.g. `scheme=`, `vmin=`, `vmax=`.

    Returns:
        matplotlib.axes.Axes: the axes drawn into.

    Raises:
        ImportError: if the `[spatial]` extra is not installed.
        ValueError: if `value` is not available.

    Example:
        >>> import starsim_data as ssd
        >>> ax = ssd.choropleth('kenya', level=1)   # doctest: +SKIP
    """
    if shapes is None:
        shapes = ssd.fetch_shapes(location, level=level)
        if value == 'population':
            nodes = ssd.fetch_nodes(location, level=level)
            shapes = shapes.merge(nodes[['pcode', 'population']], on='pcode', how='left')
    if value not in shapes.columns:
        available = [c for c in shapes.columns if c != 'geometry']
        raise ValueError(f'{value!r} is not a column of the shapes; available: {available}')

    if ax is None:
        fig_kw = sc.mergedicts(dict(figsize=(7, 7), layout='constrained'), fig_kw)
        _, ax = plt.subplots(**fig_kw)
    legend_kwds = dict(label=value.replace('_', ' ').capitalize(), shrink=0.7)
    shapes.plot(column=value, ax=ax, cmap=cmap, legend=True, edgecolor='white', linewidth=0.3, legend_kwds=legend_kwds, **kwargs)
    ax.set_axis_off()
    ax.set_title(f'{shapes.location.iloc[0]}, level {level}')
    return ax
