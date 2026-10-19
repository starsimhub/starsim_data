"""
Download subnational data from epydemix-data into `raw_data/`.

Dev/CI tool -- NOT part of the installed package. epydemix-data is where the national
contact matrices came from; it also has the Mistry et al. 2021 matrices for every US
state, and each state's population by single year of age (US Census Bureau estimates,
2023). This copies both, from a pinned commit, into the layout the build reads:

- `raw_data/contact_matrices/<Country>__<Unit>/mistry2021_us_contacts_<kind>.csv`, the
  matrices, unchanged (`__` stands for the `:` of the location key, which a folder name
  can't hold on every platform);
- `raw_data/population_us.csv`, the populations, as `location, age, population`.

Each unit is checked against the bundled node table, so that a location key here is
always the `dot_name` of a node.

Usage:

```bash
python scripts/download_epydemix.py      # -> raw_data/
python scripts/build_hdf5.py --fetched   # -> fetched/mistry2021_us.h5, fetched/population_us.h5
```
"""

import csv
import io
import sciris as sc
import starsim_data as ssd

REPO       = sc.thispath(__file__).parent
CONTACT    = REPO / 'raw_data' / 'contact_matrices'
POPULATION = REPO / 'raw_data' / 'population_us.csv'

# The epydemix-data commit to copy from (v1.2.0), so that a rerun gives the same files
COMMIT = 'e5c17e80e6d1384a6e54e177687aababb42e3f16'
URL = f'https://raw.githubusercontent.com/epistorm/epydemix-data/{COMMIT}/'

COUNTRY = 'United_States'
SOURCE = 'mistry2021_us' # The name of the dataset these matrices become
KINDS = ['all', 'home', 'work', 'school', 'community']


def get(path):
    """ Read one file of epydemix-data at the pinned commit """
    return sc.urlopen(URL + path, timeout=60, die=True)


def units():
    """ The country's level-1 units in epydemix-data, as `Country__Unit` folder names """
    rows = csv.DictReader(io.StringIO(get('locations.csv')))
    return sorted(row['location'] for row in rows if row['level'] == '1' and row['location'].startswith(f'{COUNTRY}__'))


def check(folders):
    """ Every unit must be a node, under the same name """
    nodes = set(ssd.load_nodes(COUNTRY, level=1).dot_name)
    missing = [f for f in folders if f.replace('__', ':') not in nodes]
    if missing:
        raise ValueError(f'not in the node table under these names: {missing}; map them to its dot_names before building')
    return


def main():
    folders = units()
    check(folders)
    print(f'Downloading {len(folders)} units of {COUNTRY} from epydemix-data@{COMMIT[:7]}')
    rows = []
    for folder in folders:
        out = CONTACT / folder
        out.mkdir(parents=True, exist_ok=True)
        for kind in KINDS:
            text = get(f'data/{folder}/contact_matrices/mistry_2021/contacts_matrix_{kind}.csv')
            (out / f'{SOURCE}_contacts_{kind}.csv').write_text(text)
        ages = csv.DictReader(io.StringIO(get(f'data/{folder}/demographic/age_distribution.csv')))
        for row in ages:
            rows.append(dict(location=folder.replace('__', ':'), age=row['group_name'].rstrip('+'), population=row['value']))
        print(f'  {folder}')

    with open(POPULATION, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['location', 'age', 'population'])
        writer.writeheader()
        writer.writerows(rows)
    print(f'  {POPULATION.relative_to(REPO)}: {len(rows)} rows')
    print('Done. Now run: python scripts/build_hdf5.py --fetched')
    return


if __name__ == '__main__':
    main()
