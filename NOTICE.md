# Data licensing and attribution

This repository aggregates third-party contact-matrix datasets. The repository's own code, packaging, and curation are licensed under the MIT License (see [LICENSE](LICENSE)). The **data files under `data/` are not MIT-licensed** — each dataset retains the license and copyright of its original authors, as listed below. This is a mere aggregation of independent datasets; bundling them here does not relicense any of them.

If you use these data, you must comply with the applicable upstream license and cite the corresponding paper.

## Sources

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

## Provenance

The data in this repository was derived from [epistorm/epydemix-data](https://github.com/epistorm/epydemix-data) (GPL-3.0 — full text in [licenses/LICENSE_EPYDEMIX](licenses/LICENSE_EPYDEMIX)), trimmed to national-level (level 0) contact matrices only and reorganized into a flattened file layout. Demographic data, subnational data, and the `litvinova_2025` source from the upstream repository are not included here.
