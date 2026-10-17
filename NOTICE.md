# Data licensing and attribution

This repository aggregates third-party demographic and contact-matrix datasets. The repository's own code, packaging, and curation are licensed under the MIT License (see [LICENSE](LICENSE)). The **bundled data files are not MIT-licensed** — each dataset retains the license and copyright of its original authors, as listed below. This is a mere aggregation of independent datasets; bundling them here does not relicense any of them.

If you use these data, you must comply with the applicable upstream license and cite the corresponding paper.

Of the contact matrices, only `prem2021` is bundled in the installed package. `prem2017` and `mistry2021` are distributed from this repository (in `fetched/`) and downloaded by `fetch()` on first use; they are redistributed under the same terms, below.

## Sources

### Demographics — UN World Population Prospects 2024 (CC BY 3.0 IGO)

- **Data source:** [UN World Population Prospects 2024](https://population.un.org/wpp/), United Nations, Department of Economic and Social Affairs, Population Division.
- **Indicators used:** crude birth rate (CBR), crude net-migration rate (CNMR), age/sex mortality rate `m(x)` (abridged life table), and population by 5-year age groups and sex — Medium variant, 1950–2100.
- **License / terms:** distributed under the [UN WPP terms of use](https://population.un.org/wpp/) (Creative Commons Attribution 3.0 IGO, CC BY 3.0 IGO).
- **Citation:** United Nations, Department of Economic and Social Affairs, Population Division (2024). *World Population Prospects 2024.*

### `mistry2021` — Mistry et al. 2021 (Apache-2.0)

- **Data source:** [mobs-lab/mixing-patterns](https://github.com/mobs-lab/mixing-patterns)
- **License:** Apache License 2.0 — full text in [licenses/LICENSE_MISTRY2021](licenses/LICENSE_MISTRY2021) ([upstream](https://github.com/mobs-lab/mixing-patterns/blob/main/LICENSE))
- **Paper:** Mistry D, Litvinova M, Pastore y Piontti A, et al. *Inferring high-resolution human mixing patterns for disease modeling.* Nature Communications 12, 323 (2021). https://www.nature.com/articles/s41467-020-20544-y
- **Format:** 85×85 matrices; single-year age groups (0–84, last group is 84+).

The Apache-2.0 license requires that its copyright notice, this attribution, and any applicable NOTICE be preserved on redistribution.

### `prem2021` — Prem et al. 2021 (GPL-3.0)

- **Data source:** [kieshaprem/synthetic-contact-matrices](https://github.com/kieshaprem/synthetic-contact-matrices)
- **License:** GNU General Public License v3.0 — full text in [licenses/LICENSE_PREM2021](licenses/LICENSE_PREM2021) ([upstream](https://github.com/kieshaprem/synthetic-contact-matrices/blob/master/LICENSE))
- **Paper:** Prem K, Zandvoort K van, Klepac P, et al. *Projecting contact matrices in 177 geographical regions: An update and comparison with empirical data for the COVID-19 era.* PLoS Computational Biology 17(7): e1009098 (2021). https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009098
- **Format:** 16×16 matrices; 5-year age groups (0–4, 5–9, …, 75+).

### `prem2017` — Prem et al. 2017 (GPL-3.0)

- **Data source:** [kieshaprem/synthetic-contact-matrices](https://github.com/kieshaprem/synthetic-contact-matrices)
- **License:** GNU General Public License v3.0 — full text in [licenses/LICENSE_PREM2017](licenses/LICENSE_PREM2017) ([upstream](https://github.com/kieshaprem/synthetic-contact-matrices/blob/master/LICENSE))
- **Paper:** Prem K, Cook AR, Jit M. *Projecting social contact matrices in 152 countries using contact surveys and demographic data.* PLoS Computational Biology 13(9): e1005697 (2017). https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005697
- **Format:** 16×16 matrices; 5-year age groups (0–4, 5–9, …, 75+).

### Node table — UNOCHA COD-AB (CC BY 3.0 IGO), geoBoundaries (CC BY 4.0) and WorldPop (CC BY 4.0)

The bundled `nodes.h5` (centroids, areas, populations, p-codes and hierarchy for administrative levels 0 and 1) and `adjacency.h5` (which units share a border) are **derived data**: they are computed from the boundary sources below, and the level-1 populations from WorldPop's 2020 1 km UN-adjusted rasters summed within each unit; none of the sources is itself redistributed. Every row records which boundary source it came from, in its `source` column.

- **UNOCHA COD-AB** — Common Operational Datasets, Administrative Boundaries, via the [laser-base/unocha](https://github.com/laser-base/unocha) mirror of the [UNOCHA Humanitarian Data Exchange](https://data.humdata.org/). License: Creative Commons Attribution 3.0 IGO. **Citation:** United Nations Office for the Coordination of Humanitarian Affairs (UNOCHA), *Common Operational Datasets — Administrative Boundaries (COD-AB).*
- **geoBoundaries CGAZ v6.0.0** (gbOpen) — [geoboundaries.org](https://www.geoboundaries.org). License: Creative Commons Attribution 4.0. **Citation:** Runfola D, Anderson A, Baier H, et al. *geoBoundaries: A global database of political administrative boundaries.* PLoS ONE 15(4): e0231866 (2020). https://doi.org/10.1371/journal.pone.0231866

- **WorldPop** — 1 km gridded population, [worldpop.org](https://www.worldpop.org), for the level-1 populations. License: Creative Commons Attribution 4.0. **Citation:** WorldPop (www.worldpop.org), School of Geography and Environmental Science, University of Southampton. https://dx.doi.org/10.5258/SOTON/WP00645

All three licenses permit redistribution of derived works with attribution, which is what this section provides.

## Fetched, never redistributed

These are **not** bundled with the package. They are downloaded to a local cache when you call `fetch_shapes()`, `fetch_raster()` or `fetch_nodes()`, and the terms below are yours to comply with as the person who fetched them.

- **GADM v4.1** — [gadm.org](https://gadm.org). **Free for non-commercial use only; redistribution is not permitted.** This package therefore never bundles GADM data, never derives bundled data from it, and never reaches it through the automatic source fallback — `source='gadm'` must be asked for explicitly. The constraint is enforced in code, via `ShapeSource.redistributable`. **Citation:** GADM database of Global Administrative Areas, version 4.1.
- **WorldPop** — 1 km gridded population, [worldpop.org](https://www.worldpop.org). License: Creative Commons Attribution 4.0. **Citation:** WorldPop (www.worldpop.org), School of Geography and Environmental Science, University of Southampton. https://dx.doi.org/10.5258/SOTON/WP00645
- **UN WPP bulk CSVs** — the same UN WPP 2024 release and terms as the bundled demographics above, at annual resolution.

## Provenance

The **contact matrices** were derived from [epistorm/epydemix-data](https://github.com/epistorm/epydemix-data) (GPL-3.0 — full text in [licenses/LICENSE_EPYDEMIX](licenses/LICENSE_EPYDEMIX)), trimmed to national-level (level 0) matrices only and reorganized into a flattened file layout. Subnational data, the `litvinova_2025` source, and epydemix-data's own demographic/age-distribution files are not included; the **demographic data** in this package comes from the UN World Population Prospects (above) instead.
