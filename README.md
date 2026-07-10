# Starsim Data

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

National-level population contact matrices for epidemic modeling and simulation with [Starsim](https://starsim.org). This repository is a trimmed, reorganized subset of [epydemix-data](https://github.com/epistorm/epydemix-data): it contains **national (country-level) contact matrices only**, with a flattened file layout for simple loading.

Contact matrices describe the average number of contacts between individuals in different age groups across settings (home, work, school, community, and all settings combined). They are sourced from the following studies:

- [Inferring high-resolution human mixing patterns for disease modeling](https://www.nature.com/articles/s41467-020-20544-y) (`mistry2021`) — 85×85, single-year age groups (0–84, last group is 84+).
- [Projecting contact matrices in 177 geographical regions: an update and comparison with empirical data for the COVID-19 era](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009098) (`prem2021`) — 16×16, 5-year age groups (0–4, 5–9, …, 75+).
- [Projecting social contact matrices in 152 countries using contact surveys and demographic data](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005697) (`prem2017`) — 16×16, 5-year age groups (0–4, 5–9, …, 75+).

When using these contact matrices, please cite the relevant paper(s) for each source you use. See [NOTICE.md](NOTICE.md) for full attribution and per-source data licenses.

## What's included (and what isn't)

Relative to upstream [epydemix-data](https://github.com/epistorm/epydemix-data), this repository is deliberately minimal:

- ✅ **National (level 0) contact matrices** for 187 countries.
- ✅ Sources `mistry2021`, `prem2021`, `prem2017` (whichever are available per country).
- ❌ No demographic / age-distribution data.
- ❌ No subnational data (states, provinces, US counties).
- ❌ No `litvinova_2025` source or US sex/race-ethnicity attributes.

## File layout

Each country has its own folder containing one CSV per (source, setting) combination. There are no nested subfolders:

```
data/
├── locations.csv
├── United_States/
│   ├── mistry2021_contacts_all.csv
│   ├── mistry2021_contacts_home.csv
│   ├── mistry2021_contacts_work.csv
│   ├── mistry2021_contacts_school.csv
│   ├── mistry2021_contacts_community.csv
│   ├── prem2021_contacts_all.csv
│   ├── prem2021_contacts_home.csv
│   ├── ...
│   └── prem2017_contacts_community.csv
├── Sierra_Leone/
│   ├── prem2021_contacts_all.csv
│   └── ...
└── ...
```

File names follow the pattern `<source>_contacts_<setting>.csv`, where:

- `<source>` is one of `mistry2021`, `prem2021`, `prem2017`.
- `<setting>` is one of `all`, `home`, `work`, `school`, `community`.

Each CSV is a square matrix of contact rates (no header, no index) that can be loaded directly with NumPy or pandas.

## Supported geographies

The [`data/locations.csv`](data/locations.csv) file lists the available countries and which contact sources each one has. Country names use `_` for spaces within a name (e.g. `Sierra_Leone`, `South_Africa`). All entries are level 0 (country).

| Column | Description |
|---|---|
| `location` | Country name (folder name), using `_` for spaces. |
| `level` | Geographic granularity; always `0` (country) in this repository. |
| `iso_code` | [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) country code (e.g. `US`, `DE`, `GB`). |
| `primary_contact_source` | The recommended default contact source for the country. |
| `contact_sources` | Pipe-separated list of all available sources for the country (e.g. `prem2021\|prem2017`). |
| `population_source` | Source of the underlying population data. |

## Usage

Load a contact matrix directly from the CSV files:

```python
import numpy as np

def load_contact_matrix(location, source, setting="all", data_dir="data"):
    """Load a square contact matrix as a NumPy array."""
    path = f"{data_dir}/{location}/{source}_contacts_{setting}.csv"
    return np.loadtxt(path, delimiter=",")

# Example: home contacts for the United States (Mistry 2021, 85x85)
M = load_contact_matrix("United_States", "mistry2021", "home")
print(M.shape)  # (85, 85)
```

## License

The repository's code, packaging, and curation are licensed under the [MIT License](LICENSE).

The contact-matrix data files are third-party datasets distributed under their own upstream licenses — **Apache-2.0** for `mistry2021` and **GPL-3.0** for `prem2017`/`prem2021` — not under MIT. The full text of each upstream license is in the [`licenses/`](licenses/) folder, and [NOTICE.md](NOTICE.md) has the per-source details and required attributions.
