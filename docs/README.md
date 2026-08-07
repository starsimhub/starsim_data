# docs

Quarto sources for the parts of the documentation that are too long for the README.

- [`datasources.qmd`](datasources.qmd) — what each upstream data source is good at, where it falls down, how they compare, and which one to reach for. Adapted from [`laser-init`](https://github.com/laser-base/laser-init)'s `docs/datasources.md` and extended to cover this package's sources.

Render with:

```bash
quarto render docs        # -> docs/_site/
quarto preview docs       # live reload
```

Quarto rather than mkdocs, to match [Starsim's docs](https://github.com/starsimhub/starsim/tree/main/docs). The pages carry no site chrome of their own so they can be included from the Starsim site.
